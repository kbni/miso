import os
import logging
import importlib
import socket
import traceback

from nameko.extensions import DependencyProvider

from miso.provider.redis import Redis
from miso.utils import md5file, epoch


IGNORE_MODULES = []
LOG = logging.getLogger(__name__)


def discover_services_in_path(service_path):
    try_paths = []
    for (fulldir, dirs, files) in os.walk(service_path):
        if '__init__.py' in files:
            module_path = fulldir[len(service_path) + 1:].replace('/', '.')
            try_paths.append(module_path)
            for fn in files:
                if fn != '__init__.py' and fn.endswith('.py'):
                    try_paths.append(f'{module_path}.{fn[0:-3]}')

    for import_path in try_paths:
        for service in extract_services(import_path):
            yield service


def extract_services(import_path):
    if import_path.startswith('_') or import_path.startswith('restie'):
        return
    try:
        module = importlib.import_module(import_path)
        importlib.reload(module)
    except:  # noqa: E722 (Any single exception when importing modules should result in failure!)
        traceback.print_exc()
        LOG.exception('Failed to import %s', import_path)
        return
    for obj_name in dir(module):
        ps = getattr(module, obj_name)
        psname = getattr(ps, 'name', None)
        if psname and (psname == 'AuthService' or hasattr(ps, '_miso_service_obj')):
            yield module, ps


class ServiceStore:
    def __init__(self, from_modules=None):
        self.services = []
        self.file_mtimes = {}

        if from_modules is not None:
            for module_name in from_modules:
                for module, service in extract_services(module_name):
                    self.add_module(service, module)

    def should_reload(self):
        should_reload = False
        for fn, old_mtime in self.file_mtimes.items():
            if os.path.getmtime(fn) != old_mtime:
                should_reload = True
                LOG.info('Detected modified file: %s', fn)
        return should_reload

    def add_module(self, service, module):
        if module.__file__ not in self.file_mtimes:
            self.file_mtimes[module.__file__] = os.path.getmtime(module.__file__)
        self.services.append(service)


class State:
    _instances = {}
    _services = {}

    def __init__(self, redis):
        self.redis = redis
        self.logger = logging.getLogger(__name__)
        self.master_node = None

    @classmethod
    def get_state(cls, container=None, config=None):
        redis = Redis.get_redis(container=container, config=config)
        if repr(redis) not in cls._instances:
            cls._instances[repr(redis)] = State(redis)
        return cls._instances[repr(redis)]

    def update_environment(self):
        os.environ['MISO_CLUSTER_ID'] = self.cluster_id
        os.environ['MISO_NODE_ID'] = self.node_id
        os.environ['MISO_NODE_ADDRESS'] = self.node_address

    def update(self, **kwargs):
        for key, val in kwargs.items():
            self.redis.setj(f'miso:nodes:{self.node_id}:{key}', val)

    def get_active_nodes(self, threshold=30):
        """ Returns a list of nodes that have been active within the last threshold (120) seconds
        -> [(1629312332, 'node-id')] """
        now = epoch()
        other_nodes = []
        for node_id in self.redis.keys('miso:nodes:*:last_seen', idx=-2):
            last_seen = self.redis.getj(f'miso:nodes:{node_id}:last_seen')
            if last_seen and now - last_seen < threshold:
                other_nodes.append((last_seen, node_id))
        return sorted(other_nodes)

    def confirm_master(self):
        now = epoch()
        if not self.master_node:
            self.master_node = self.redis.get('miso:cluster:master_node')
        if self.master_node:
            master_last_seen = now - self.redis.getj(f'miso:nodes:{self.master_node}:last_seen')
            if master_last_seen is None or master_last_seen > 20:
                self.logger.warning('We %s have not seen our master (%s) for 20 seconds now', id(self), self.master_node)
                self.master_node = None
        if not self.master_node:
            for last_seen, other_node in self.get_active_nodes():
                if self.redis.getj(f'miso:nodes:{other_node}:never_promote'):
                    continue  # This node does not want to be master, move on!
                self.redis.set('miso:cluster:master_node', other_node)
                self.master_node = other_node
                self.logger.info('%s has been nominated as master by %s', other_node, self.node_id)
                break
        return self.master_node

    def requires_restart(self):
        required = self.redis.getj('miso:cluster:requires_restart')
        if required:
            self.redis.setj('miso:cluster:requires_restart', False)
        return required

    def get_available_services(self):
        for service_name, service_class, service_file, module in discover_services_in_path(self.service_path):
            file_hash = md5file(service_file)
            file_mtime = int(os.stat(service_file).st_mtime)
            file_key = f'{service_file}'[(len(self.service_path) + 1):]

            old_mtime = self.redis.getj(f'miso:services:{service_name}:mtime')
            self.redis.setj(f'miso:services:{service_name}:file_key', file_key)
            self.redis.setj(f'miso:services:{service_name}:last_seen', epoch())
            if not old_mtime or old_mtime < file_mtime:
                self.redis.setj(f'miso:services:{service_name}:mtime', file_mtime)
                self.redis.setj(f'miso:services:{service_name}:hash', file_hash)
                if old_mtime:
                    self.logger.debug('Reloading %s due to mtime', module)
                    importlib.reload(module)

            self._services[service_name] = {
                'class': service_class,
                'file': service_file,
                'hash': file_hash,
                'load_hash': self.redis.getj(f'miso:services:{service_name}:hash')
            }

        return [self._services[svc]['class'] for svc in self._services]

    @property
    def node_id(self):
        id_ = os.environ.get('MISO_NODE_ID', '{HOSTNAME}.{PID}')
        id_ = id_.replace('{HOSTNAME}', socket.gethostname().split('.')[0])
        id_ = id_.replace('{PID}', str(os.getpid()))
        return id_

    @property
    def cluster_id(self):
        return os.environ.get('MISO_CLUSTER_ID', 'miso')

    @property
    def node_address(self):
        address = os.environ.get('MISO_ADDRESS', '0.0.0.0')
        if address == '0.0.0.0':
            try:
                address = socket.gethostbyname(socket.gethostname()) + ':' + address.split(':')[-1]
            except:  # noqa: E722 (sockets, timeouts, IO, whatever...)
                # If DNS is misconfigured on this host, attempt to open a socket to Google's DNS
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                address = s.getsockname()[0]
                s.close()
        if not address:
            self.logger.warning('Unable to determine hostname in Miso State')
        return address or 'localhost'

    @property
    def service_path(self):
        return os.environ.get('MISO_SERVICE_PATH', os.path.dirname(os.path.dirname(__file__)))

    @property
    def is_master(self):
        return self.master_node == self.node_id


class StateProvider(DependencyProvider):
    def get_dependency(self, worker_ctx):
        return State.get_state(container=worker_ctx.container)

