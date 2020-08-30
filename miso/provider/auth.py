
import os
import jwt
from logging import getLogger

from nameko.rpc import rpc
from nameko.extensions import DependencyProvider
from nameko.standalone.rpc import ClusterRpcProxy

from miso.utils import ensure_bytes, ensure_str
from miso.provider.redis import Redis
from miso.encoder import register_better_json


LOG = getLogger('miso.provider.auth')
register_better_json()


def forge_token(secret, tenant_id, username='SYSTEM', roles=[]):
    user_info = {
        'tenant_id': tenant_id,
        'username': username,
        'roles': roles
    }
    return ensure_str(jwt.encode(user_info, secret))


class NotAuthenticated(Exception):
    pass


class AuthProxy:
    def __init__(self, token, config):
        self.token = token
        self.config = config
        self.proxy = ClusterRpcProxy(config, context_data={'miso_auth_token': self.token})
        self.rpc = self.proxy.start()

    def stop(self):
        self.proxy.stop()


class Auth:
    def __init__(self, redis, token):
        self.redis = redis
        self._token = token
        self._secret = os.environ.get('MISO_SECRET_KEY', self.redis.get('miso:cluster:secret_key'))
        self._session = None

    @classmethod
    def from_context(cls, worker_ctx):
        redis = Redis.get_redis(worker_ctx.config)
        return Auth(redis, token=worker_ctx.context_data.get('miso_auth_token'))

    def apply_to_context(self, worker_ctx, token=None):
        if token:
            self.assume(token)
        else:
            token = self.token
        if token:
            worker_ctx.context_data['miso_auth_token'] = token

    def login(self, tenant_id, username, password):
        if not username or not tenant_id:
            return False

        user_key = f'miso:tenants:{tenant_id}:users:{username}'
        tenant_enabled = self.redis.getj(f'miso:tenants:{tenant_id}:enabled')
        user_enabled = self.redis.getj(f'{user_key}:enabled')
        user_password = self.redis.getj(f'{user_key}:password')
        user_roles = self.redis.getj(f'{user_key}:roles') or []

        if not user_enabled:
            LOG.error('username is disabled: %s (%s)', username, tenant_id)
            return False

        if not tenant_enabled:
            LOG.error('tenant is disabled: %s', tenant_id)
            return False

        if password == user_password:
            LOG.debug('authenticated as %s (%s)', username, tenant_id)
            self._token = forge_token(tenant_id, username, user_roles)
            return True

        LOG.error('unsuccessful auth attempt for %s ( tenant %s)', username, tenant_id)
        return False

    def assume(self, token):
        self._token = token
        self._session = self.parse_token(token)

    def forge_token(self, *args):
        return forge_token(self.secret, *args)

    def parse_token(self, token):
        if token:
            try:
                return jwt.decode(ensure_bytes(token), self.secret)
            except jwt.exceptions.DecodeError:
                print('unable to parse token: token')
                return None

    def user_is(self, role):
        return self.session and role in self.session['roles']

    def user_can(self, perm):
        return self.session and perm in self.session['permissions']

    def whoami(self):
        if self.session:
            return f'{self.username}@{self.tenant_id}'
        else:
            return 'nobody'

    @property
    def secret(self):
        if self._secret:
            return self._secret
        else:
            LOG.warning('We were unable to retrieve a real secret from Redis')
            return 'Default_Secret'

    @property
    def token(self):
        if self._token:
            return ensure_str(self._token)

    @property
    def session(self):
        if self._session is None and self._token is not None:
            self._session = self.parse_token(self._token)
        return self._session

    @property
    def tenant_id(self):
        if self.session:
            return self.session['tenant_id']

    @property
    def authenticated(self):
        if self.session:
            return True
        return False

    @property
    def username(self):
        if self.session:
            return self.session['username']

    @property
    def roles(self):
        if self.session:
            return self.session['roles']


class AuthProvider(DependencyProvider):
    """ DependencyProvider giving services access to the current session. """
    def get_dependency(self, worker_ctx):
        return Auth.from_context(worker_ctx)


class AuthService:
    name = 'auth'
    auth: Auth = AuthProvider()

    @rpc
    def whoami(self):
        if self.auth.tenant_id:
            return f'{self.auth.username}@{self.auth.tenant_id}'
        else:
            return 'nobody'

    @rpc
    def authenticate(self, tenant, username, password):
        self.auth.login(tenant, username, password)
        return self.auth.token

    @rpc
    def parse_token(self, token):
        return self.auth.parse_token(token)
