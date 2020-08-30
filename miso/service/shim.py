from uuid import uuid4
from logging import getLogger
from eventlet import tpool
from miso.encoder import dumps
from miso.provider.auth import Auth
from miso.provider.redis import Redis
from miso.utils import Result, comma_join, force_list, md5sum
from werkzeug.wrappers import Response


class ShimExecutor:
    shim = []
    stop_executing = False
    result = None

    def __init__(self, method, worker_ctx):
        self.logger = getLogger('miso.service')
        self.method = method
        self.options = self.method._miso_options
        self.entrypoint = worker_ctx.entrypoint
        self.worker_ctx = worker_ctx
        self.service_id = f'{worker_ctx.service.name}.{method.__name__}'
        self.execution_id = str(uuid4())
        self.shims = [shim(self) for shim in Shim.__subclasses__() if shim.enabled]

    @property
    def log_extra(self):
        extra = {
            'miso_service': self.service_id,
            'miso_exec_id': self.execution_id
        }
        for shim in self.shims:
            extra.update(**shim.log_extra())
        return extra

    def shim_lines(self):
        parts = []
        for shim in self.shims:
            if not shim.enabled:
                continue
            from_log = []
            for k, v in shim.log_extra().items():
                from_log.append(f'{k}={v}')
            if from_log:
                parts.append(f'{shim.name}:{",".join(from_log)}')
            else:
                parts.append(f'{shim.name}')
        return ' '.join(parts)

    def call(self):
        return self.method(*self.worker_ctx.args, **self.worker_ctx.kwargs)

    def apply(self):
        self.logger.info(f'Call to {self.service_id} ({self.execution_id}) started', extra=self.log_extra)

        for shim in self.shims:
            if shim.enabled:
                shim.pre_call()

        try:
            for shim in self.shims:
                if self.stop_executing:
                    # self.logger.debug('no longer doing pre_execute()s due to stop_executing')
                    break
                if shim.enabled:
                    shim.pre_execute()

            for shim in self.shims:
                if self.stop_executing or shim.alternate_execute():
                    break
            if not self.stop_executing:
                self.result = self.call()

            for shim in reversed(self.shims):
                if self.stop_executing:
                    # self.logger.debug('no longer doing post_execute()s due to stop_executing')
                    break
                if shim.enabled:
                    shim.post_execute()
        except:  # noqa: E722
            self.logger.exception('service raised an exception!', extra=self.log_extra)
            self.result = Result(result=False, reason='exception in the called service')

        for shim in reversed(self.shims):
            if shim.enabled:
                shim.post_call()

        self.logger.info(
            f'Call to {self.service_id} ({self.execution_id}) ended: ({self.shim_lines()})', extra=self.log_extra
        )

        return self.result


class Shim:
    name = None
    enabled = False

    def __init__(self, override):
        self.override = override
        self.logger = override.logger

    def __repr__(self):
        return f'<{self.__class__.__name__}(enabled={self.enabled})>'

    def post_call(self):
        pass

    def pre_call(self):
        pass

    def pre_execute(self):
        pass

    def post_execute(self):
        pass

    def alternate_execute(self):
        return False

    def log_extra(self):
        return {}

    def stop_execution(self):
        self.override.stop_executing = True

    def set_result(self, result, stop_executing=False):
        self.override.result = result
        self.override.stop_executing = stop_executing

    def set_fail(self, reason):
        self.override.result = Result(result=False, reason=reason)
        self.override.stop_executing = True


class AuthShim(Shim):
    name = 'auth'
    enabled = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.auth: Auth = getattr(self.override.worker_ctx.service, 'auth', None)
        self.require_auth = self.override.options.require_auth
        self.require_role = self.override.options.require_role
        self.require_tenant = self.override.options.require_tenant
        self.sudo = self.override.options.sudo
        self.check_auth = bool(self.require_auth or self.require_role or self.require_tenant)
        self.enabled = self.sudo or self.check_auth

    def log_extra(self):
        return {
            'tenant': self.auth.tenant_id,
            'user': self.auth.username,
            'authenticated': int(bool(self.auth.session))
        }

    def pre_call(self):
        if self.sudo:
            self.auth.assume(self.auth.forge_token(*force_list(self.sudo)))
            self.auth.apply_to_context(self.override.worker_ctx)

        if self.check_auth:
            issues = {}
            if not self.auth:
                issues['NOOBJ'] = 'Auth object not attached to service'
                self.set_fail('authentication required')
            else:
                if self.require_auth and not self.auth.authenticated:
                    issues['NOAUTH'] = 'Available only to authenticated callers'
                if self.require_role:
                    matching_roles = [role for role in force_list(self.require_role) if role in (self.auth.roles or [])]
                    if not matching_roles:
                        issues['MROLES'] = f'Does not have roles: {comma_join(self.require_role)}'

                if self.require_tenant and self.require_tenant != self.tenant_id:
                    issues['WTENANT'] = 'Tenant does not have access to service!'

                if issues:
                    self.set_fail('permission denied')

            if issues:
                self.logger.error(f'authentication failure in service: %s', ','.join(issues.keys()))


class ThreadingShim(Shim):
    name = 'thread'
    enabled = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enabled = self.override.options.threaded is True

    def alternate_execute(self):
        if self.enabled:
            self.set_result(tpool.execute(self.override.call), stop_executing=True)
            return True
        return False

    def log_extra(self):
        return {
            'threaded': int(self.enabled)
        }


class CachingShim(Shim):
    name = 'cache'
    enabled = True
    call_hash = None
    cache_key = None
    retrieved = False
    stored = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.redis: Redis = getattr(self.override.worker_ctx.service, 'redis', None)
        self.auth: Auth = getattr(self.override.worker_ctx.service, 'auth', None)
        self.cache_time = self.override.options.cache_time
        self.cache_allow_override = self.override.options.cache_allow_override
        self.enabled = bool(self.cache_time or self.cache_allow_override)
        if self.enabled:
            self.call_hash = md5sum(dumps({
                'service_id': self.override.service_id,
                'args': self.override.worker_ctx.args,
                'kwargs': self.override.worker_ctx.kwargs,
                'username': self.auth.username,
                'teant_id': self.auth.tenant_id
            }))
            self.cache_key = f'miso:cache:{self.override.worker_ctx.service.name}:{self.call_hash}'

    def log_extra(self):
        return {
            'from_cache': int(self.retrieved),
            'to_cache': int(self.stored)
        }

    def pre_call(self):
        cached_data = self.redis.getj(f'{self.cache_key}:data')
        if cached_data:
            self.set_result(cached_data, stop_executing=True)
            self.retrieved = True

    def post_execute(self):
        if not self.retrieved and self.cache_time:
            self.stored = True
            self.redis.setj(f'{self.cache_key}:data', self.override.result)
            self.redis.expire(f'{self.cache_key}:data', self.cache_time)


class ForceObject(Shim):
    name = 'forceobj'
    enabled = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enabled = self.override.options.force_res_object

    def post_call(self):
        if self.enabled and not isinstance(self.override.result, (Response, Result)):
            if isinstance(self.override.result, bool):
                self.override.result = Result(result=self.override.result)
            else:
                self.override.result = Result(result=True, data=self.override.result)
