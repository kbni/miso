import json
from logging import getLogger
from nameko.extensions import DependencyProvider
from redis import StrictRedis
from miso.encoder import JSONDecoder, JSONEncoder


LOG = getLogger('miso.provider.redis')


class RedisProvider(DependencyProvider):
    client = None

    def start(self):
        self.client = Redis.get_redis(container=self.container)

    def get_dependency(self, worker_ctx):
        return self.client


class Redis:
    _instances = {}

    def __init__(self, config):
        self.logger = getLogger('miso.provider.redis')
        self.conn = StrictRedis.from_url(
            config['MISO_REDIS']['url'],
            **config['MISO_REDIS'].get('options', {})
        )

    @classmethod
    def get_redis(cls, config=None, container=None):
        if container is not None:
            config = container.config
        if config is None:
            raise ValueError('Could not acquire configuration object from supplied arguments!')

        redis_uri = config['MISO_REDIS']['url']
        if redis_uri not in cls._instances:
            cls._instances[redis_uri] = Redis(config)
        return cls._instances[redis_uri]

    def set_type(self, name, val, type_obj):
        if not name.startswith('miso:'):
            self.logger.debug('set_type: %s : %s = %s', name, type_obj, val)
        if type_obj == 'json':
            val = json.dumps(val, cls=JSONEncoder, sort_keys=True, indent=2)
        else:
            val = type_obj(val)
        return self.conn.set(name, val)

    def get_type(self, name, type_obj):
        if not name.startswith('miso:'):
            self.logger.debug('get_type: %s - %s waiting..', name, type_obj)
        val = self.conn.get(name)
        if type_obj == 'json':
            if val is not None:
                val = json.loads(val, cls=JSONDecoder)
        else:
            val = type_obj(val)
        if not name.startswith('miso:'):
            self.logger.debug('get_type: %s - %s returned %s', name, type_obj, val)
        return val

    def getj(self, name):
        return self.get_type(name, 'json')

    def setj(self, name, val):
        return self.set_type(name, val, 'json')

    def keys(self, key_search, idx=None):
        for key in self.conn.keys(key_search):
            if idx is None:
                yield key
            else:
                yield key.split(':')[idx]

    def __getattr__(self, name):
        return getattr(self.conn, name)

