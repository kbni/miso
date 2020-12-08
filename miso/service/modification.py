import sys
import types
import functools
from nameko.containers import _log, _log_time, ServiceContainer
from nameko.rpc import Rpc, RpcProxy
from nameko.timer import Timer
from nameko.web.handlers import HttpRequestHandler
from nameko.web.server import WebServer
from nameko.extensions import register_entrypoint
from werkzeug.wrappers import Response
from miso.utils import Result
from miso.service.shim import ShimExecutor
from miso.encoder import dumps
from miso.state import State


class MisoOverrideOptions:
    require_auth = None
    require_role = None
    require_tenant = None
    force_res_object = True
    cache_time = 0
    cache_allow_override = None
    threaded = None
    master_only = False
    sudo = None

    def __repr__(self):
        options = ' '.join(f'{p}={getattr(self, p)}' for p in dir(self) if not p.startswith('_'))
        return f'<{self.__class__.__name__} {options}>'


class MisoEntrypointModifications:
    @classmethod
    def decorator(cls, *args, **kwargs):
        def register_miso_entrypoint(fn, args, kwargs, cls):
            if not hasattr(fn, '_miso_options'):
                fn._miso_options = MisoOverrideOptions()
                fn._master_only = fn._miso_options.master_only

            for prop in [p for p in dir(MisoOverrideOptions) if not p.startswith('_')]:
                if prop in kwargs:
                    setattr(fn._miso_options, prop, kwargs[prop])
                    del kwargs[prop]

            instance = cls(*args, **kwargs)
            register_entrypoint(fn, instance)
            return fn

        if len(args) == 1 and isinstance(args[0], types.FunctionType):
            return register_miso_entrypoint(args[0], args=(), kwargs={}, cls=cls)
        else:
            return functools.partial(register_miso_entrypoint, args=args, kwargs=kwargs, cls=cls)

    def entrypoint_kwargs(self):
        return {p: getattr(self, p) for p in dir(MisoEntrypointModifications) if not p.startswith('_')}

class MisoWebServer(WebServer):
    def __init__(self):
        super().__init__()

    @property
    def sharing_key(self):
        return WebServer

    def context_data_from_headers(self, request):
        return {
            'miso_auth_token': request.headers.get('X-Auth-Token', None)
        }


class MisoHttpRequestHandler(MisoEntrypointModifications, HttpRequestHandler):
    server = MisoWebServer()

    def __init__(self, method, url, **kwargs):
        super().__init__(method, url, **kwargs)


class MisoRpc(MisoEntrypointModifications, Rpc):
    pass


class MisoTimer(MisoEntrypointModifications, Timer):
    pass


class MisoServiceContainer(ServiceContainer):
    _miso_state = None

    @property
    def miso_state(self):
        if self._miso_state is None:
            self._miso_state = State.get_state(config=self.config)
        return self._miso_state

    def _run_worker(self, worker_ctx, handle_result):
        _log.debug('enhancing call to %s.%s', worker_ctx.service.name, worker_ctx.entrypoint.method_name)
        _log.debug('setting up %s', worker_ctx)
        _log.debug('call stack for %s: %s', worker_ctx, '->'.join(worker_ctx.call_id_stack))

        with _log_time('ran worker %s', worker_ctx):
            self._inject_dependencies(worker_ctx)
            self._worker_setup(worker_ctx)

            result = exc_info = None
            method_name = worker_ctx.entrypoint.method_name
            method = getattr(worker_ctx.service, method_name)

            if isinstance(worker_ctx.entrypoint, MisoEntrypointModifications):
                result = ShimExecutor(method, worker_ctx).apply()

                # Convert any results from enhanced entrypoints to JSON if possible
                if isinstance(worker_ctx.entrypoint, MisoHttpRequestHandler):
                    status_code, headers = 200, {}

                    if isinstance(result, tuple):
                        if len(result) == 2:
                            status_code, output = result
                        else:
                            status_code, headers, output = result
                    else:
                        output = result

                    if isinstance(output, Response):
                        headers.update(output.headers)
                        output = output.get_data(as_text=True)
                    if isinstance(output, Result):
                        output = output.to_dict()
                    if isinstance(output, (dict, list)):
                        output = dumps(output, indent=2, sort_keys=True)
                    if isinstance(output, str) and output[-1] != '\n':
                        output += '\n'

                    result = status_code, headers, output
            else:
                try:
                    _log.debug('calling handler for %s', worker_ctx)
                    with _log_time('ran handler for %s', worker_ctx):
                        result = method(*worker_ctx.args, **worker_ctx.kwargs)
                except Exception as exc:
                    if (
                        hasattr(worker_ctx.entrypoint, 'expected_exceptions') and
                        isinstance(exc, worker_ctx.entrypoint.expected_exceptions)
                    ):
                        _log.warning(
                            '(expected) error handling worker %s: %s',
                            worker_ctx, exc, exc_info=True)
                    else:
                        _log.exception(
                            'error handling worker %s: %s', worker_ctx, exc)
                    exc_info = sys.exc_info()

            if handle_result is not None:
                _log.debug('handling result for %s', worker_ctx)

                with _log_time('handled result for %s', worker_ctx):
                    result, exc_info = handle_result(
                        worker_ctx, result, exc_info)

            with _log_time('tore down worker %s', worker_ctx):

                self._worker_result(worker_ctx, result, exc_info)

                # we don't need this any more, and breaking the cycle means
                # this can be reclaimed immediately, rather than waiting for a
                # gc sweep
                del exc_info

                self._worker_teardown(worker_ctx)


rpc = rpc_enhanced = MisoRpc.decorator
http = http_enhanced = MisoHttpRequestHandler.decorator
timer = timer_enhanced = MisoTimer.decorator
