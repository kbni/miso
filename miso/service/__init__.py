from logging import getLogger
from munch import munchify

from miso.utils import Result, hostname
from miso.provider import MisoProviderWrapper
from miso.provider.auth import AuthProvider, Auth
from miso.provider.redis import RedisProvider, Redis
from miso.service.modification import rpc_enhanced, http_enhanced, timer_enhanced, RpcProxy


__all__ = [
    'rpc_enhanced',
    'http_enhanced',
    'timer_enhanced',
    'Service',
    'Result',
    'RpcProxy'
]


class Service:
    name = None
    redis: Redis = RedisProvider()
    auth: Auth = AuthProvider()

    _miso_service_obj = True

    def __init__(self):
        if not self.name:
            raise ValueError('Service class has no name property')
        self.logger = getLogger(f'miso.service.{self.name}')

    @rpc_enhanced(force_res_object=True)
    def is_service_available(self) -> Result:
        ''' Simply confirms the service is available '''
        return Result(
            result=True,
            data={
                'message': f'The {self} service is available and responding!',
                'server': hostname()
            }
        )

    def construct_result(self, *args, **kwargs) -> Result:
        ''' Helper function to build a result '''
        return Result(*args, **kwargs)

    def _result(self, *args, **kwargs) -> Result:
        ''' Helper function to build a result '''
        return Result(*args, **kwargs)

    def _pipeline(self, process_steps, inputs=None):
        inputs = munchify(inputs or {})
        history = []
        reason = None

        for idx, (func, args) in enumerate(process_steps):
            history.append(munchify({
                'step': idx+1,
                'func_name': func.__func__.__name__,
                'output': None,
                'finished': False
            }))

            log_descr = f'step {history[-1].step}/{len(process_steps)} {history[-1].func_name}'
            self.logger.info('Starting %s with args: %s', log_descr, args)

            send_args = []
            for arg in args:
                scope, name = arg.split('.')
                if scope == 'input':
                    send_args.append(getattr(inputs, name, None))
                elif scope == 'last':
                    send_args.append(getattr(history[-2].output, name, None))
                else:
                    raise NameError('Only know of input and last scope for process_step args')

            output = func(*send_args)
            history[-1].finished = True
            history[-1].output = output
            self.logger.info('Finished %s; returned result=%s', log_descr, output and output.result)

            # Stop processing if the last step failed
            if not output or output.result is not True:
                reason = f'{history[-1].func_name} did not return result=True'
                break

        return self.construct_result(
            result=output and output.result is True,
            detail=munchify({'inputs': inputs, 'history': history}),
            reason=reason
        )
