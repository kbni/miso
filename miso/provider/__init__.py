from logging import getLogger
from nameko.extensions import DependencyProvider


LOG = getLogger('miso.provider')


class DynamicProvider(DependencyProvider):
    def __init__(self, klass, *args, **kwargs):
        self._klass = klass
        self._args = args
        self._kwargs = kwargs

    def setup(self):
        LOG.debug('fff')
        LOG.debug('%s.setup()', self.__class__.__name__)

    def worker_result(self, worker_ctx, result=None, exc_info=None):
        LOG.debug('%s.worker_result()', self.__class__.__name__)

    def worker_setup(self, worker_ctx):
        LOG.debug('%s.worker_setup()', self.__class__.__name__)

    def worker_teardown(self, worker_ctx):
        LOG.debug('%s.worker_teardown()', self.__class__.__name__)

    def get_dependency(self, worker_ctx):
        LOG.debug('%s.get_dependency() -> %s', self.__class__.__name__, worker_ctx.context_data)


class MisoProviderWrapper(DependencyProvider):
    def __init__(self, *args, **kwargs):
        pass

    def setup(self):
        LOG.debug('ProviderWrapper.setup()')

    def worker_result(self, worker_ctx, result=None, exc_info=None):
        LOG.debug('ProviderWrapper.worker_result()')

    def worker_setup(self, worker_ctx):
        LOG.debug('ProviderWrapper.worker_setup()')

    def worker_teardown(self, worker_ctx):
        LOG.debug('ProviderWrapper.worker_teardown()')

    def get_dependency(self, worker_ctx):
        LOG.debug('ProviderWrapper.get_dependency()')


class UppercaseProvider(DependencyProvider):
    def worker_setup(self, worker_ctx):
        LOG.debug('UppercaseProvider.worker_setup()')

    def get_dependency(self, worker_ctx):
        LOG.debug('UppercaseProvider.get_dependency()')
        print('fffff')
        return lambda x: str(x).upper()


class LowercaseProvider(DependencyProvider):
    def worker_setup(self, worker_ctx):
        LOG.debug('LowercaseProvider.worker_setup()')

    def get_dependency(self, worker_ctx):
        LOG.debug('LowercaseProvider.get_dependency()')
        return lambda x: str(x).lower()


class AuthProvider(DependencyProvider):
    pass


class RedisProvider(DependencyProvider):
    pass


"""
class AuthProvider(DependencyProvider):
    def get_dependency(self, worker_ctx):
        return Auth.from_context(worker_ctx)

class RedisProvider(DependencyProvider):
    client = None

    def start(self):
        self.client = Redis.get_redis(container=self.container)

    def get_dependency(self, worker_ctx):
        if worker_ctx.context_data.get('miso_auth_token'):

        return self.client

    def from_context(cls, worker_ctx):
        redis = Redis.get_redis(worker_ctx.config)
        return Auth(redis, token=worker_ctx.context_data.get('miso_auth_token'))

"""
