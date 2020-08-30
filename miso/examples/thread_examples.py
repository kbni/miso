import itertools
from miso.service import Service, rpc_enhanced


class ThreadExampleService(Service):
    name = 'thread_examples'

    @rpc_enhanced(threaded=True)
    def prime_threaded(self, n=1000):
        self.logger.debug("Calculating %dth prime", n)
        primes = []
        for i in itertools.count(2):
            for p in primes:
                if (i % p) == 0:
                    break
            else:
                primes.append(i)
            if len(primes) >= n:
                break
        p = primes[-1]
        self.logger.debug("%dth prime is %d", n, p)
        return p
