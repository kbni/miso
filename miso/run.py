import os
import sys
import time
import yaml
import logging
import logging.config
import argparse

from envyaml import EnvYAML
from nameko.cli.run import import_service
from nameko.runners import run_services

from .utils import epoch, is_debug_env
from .encoder import register_better_json
from .state import State, ServiceStore
from .provider.auth import AuthService


SERVICE_CONTAINER_CLS = 'miso.service.modification.MisoServiceContainer'
GLOBAL_NODE_ID = '_global'
DEFAULT_MODULES = ['miso.auth', 'miso.manager']
CHECK_MASTER_INTERVAL = 30
os.environ.setdefault('FORKED_BY_MULTIPROCESSING', '1')


class MisoRunner:
    def __init__(self, config_file=None):
        self.config = {}
        if config_file and os.path.exists(config_file):
            self.config = dict(**EnvYAML(config_file))

        logging.config.dictConfig(self.config['LOGGING'])
        register_better_json()

        self.config['SERVICE_CONTAINER_CLS'] = SERVICE_CONTAINER_CLS
        self.logger = logging.getLogger('miso.run')

        extra_path = self.config.get('EXTRA_PATH', 'extra_path')
        if os.path.exists(extra_path):
            sys.path.insert(0, os.path.abspath(extra_path))

        self.state = State.get_state(config=self.config)
        self.redis = self.state.redis
        self.auto_reload = False
        self.modules = []
        self.no_auth = False
        self.stateless = False

    def add_modules(self, module_list):
        for m in module_list:
            if m.endswith('.py'):
                if not os.path.basename(m).startswith('__'):
                    m = m.replace(os.path.sep, '.')[0:-3]
                    self.modules.append(m)

    def list_services(self):
        print('Would load the following services:')
        for service in self.get_services():
            print(f' -> {service}')

    def get_services(self):
        if self.modules:
            services = []
            if not self.no_auth:
                services.append(AuthService)
            for from_module in self.modules:
                for service_name, service_class, service_file, module in services_from_import(from_module):
                    services.append(service_class)
            return services
        else:
            return self.state.get_available_services()

    def main(self):
        if not self.stateless:
            self.state.update_environment()
            self.state.update(started=epoch(), stopped=None, ip_addr=self.state.node_address)
            self.logger.info('This instance is %s on %s', self.state.node_id, self.state.cluster_id)
        stopped = False
        while stopped is False:
            store = ServiceStore(from_modules=self.modules)
            self.logger.info('Starting nameko containers with %s', store.services)
            with run_services(self.config, *store.services, kill_on_exit=True):
                while True:
                    try:
                        if not self.stateless:
                            self.state.confirm_master()
                        time.sleep(1 if self.auto_reload else 5)
                        if self.auto_reload and store.should_reload():
                            self.logger.info('Server reload!')
                            if not self.stateless:
                                self.state.update(stopped=epoch())
                            break
                        if not self.stateless:
                            self.state.update(last_seen=epoch())
                    except KeyboardInterrupt:
                        self.logger.warning('Stopping nameko containers (someone hit ^C)')
                        if not self.stateless:
                            self.state.update(stopped=epoch())
                        stopped = True
                        break


def env_from_file(env_file, require_env=False):
    if not os.path.exists(env_file):
        if require_env:
            sys.stderr.write(f'Environment file "{env_file}" does not exist.\n')
            sys.exit(1)
        else:
            return
    with open(env_file) as fh:
        for line in fh.readlines():
            line = line.strip()
            if line and line.startswith('#include '):
                env_from_file(line.split(' ', 1)[-1])
            elif line and '=' in line and not line.startswith('#'):
                env_var, env_val = [e.strip() for e in line.split('=', 1)]
                os.environ[env_var] = env_val
                sys.stdout.write(f'setting {env_var} = {env_val} from {env_file}\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', '-c', type=str, default='./config.yml')
    parser.add_argument('--environment', '-e', type=str, default='./environment')

    parser.add_argument('--stateless', dest='stateless', action='store_const', const=True)
    parser.add_argument('--node', '-n', type=str, default=None, help='Node ID override')
    parser.add_argument('--cluster', '-k', type=str, default=None, help='Cluster ID override')

    parser.add_argument('--services', '-S', dest='list_services', action='store_const', const=True)
    parser.add_argument('--autoreload', '-R', dest='autoreload', action='store_const', const=True)
    parser.add_argument('--no-auth', dest='no_auth', action='store_const', const=True)
    parser.add_argument('--set-secret', dest='set_secret', default=None, type=str)
    parser.add_argument('modules', metavar='MODULE', type=str, nargs='*', help='modules to load services from')

    options = parser.parse_args()
    if options.cluster:
        os.environ['MISO_CLUSTER_ID'] = options.cluster
    if options.node:
        os.environ['MISO_NODE_ID'] = options.node

    env_file = os.environ.get('MISO_ENV_FILE', options.environment)
    if env_file:
        env_from_file(env_file)

    use_config = options.config
    if not os.path.exists(use_config) and os.path.exists('./miso/config.yml'):
        use_config = './miso/config.yml'
    mr = MisoRunner(use_config)

    if options.no_auth:
        mr.no_auth = True

    if options.autoreload:
        mr.auto_reload = True

    if options.stateless:
        mr.stateless = True

    modules = []
    if options.modules:
        modules = options.modules

    modules_from_env = os.environ.get('MISO_MODULES', None)
    if modules_from_env:
        modules = modules_from_env.split(' ')

    if not modules:
        sys.stderr.write("No modules specified\n")
        sys.exit(1)

    mr.add_modules(modules)

    if options.list_services:
        mr.list_services()
    else:
        mr.main()
