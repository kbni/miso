from miso.utils import sleep, epoch
from miso.service import Service, rpc_enhanced


class CacheExampleService(Service):
    name = 'cache_examples'

    @rpc_enhanced(cache_time=10)
    def epoch(self):
        return epoch()

    @rpc_enhanced(cache_time=120)
    def slow_method(self):
        sleep(5)
        return 'The slow method has completed'
