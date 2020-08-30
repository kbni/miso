import sys
import yaml

from logging import getLogger
from nameko.cli.shell import make_nameko_helper, ShellRunner, event_dispatcher, ClusterRpcProxy
from nameko.constants import AMQP_URI_CONFIG_KEY
from miso.encoder import register_better_json


LOGGER = getLogger(__name__)


class ShellHelper:
    def __init__(self, config, context_data):
        proxy = ClusterRpcProxy(config, context_data=context_data)
        self.rpc = proxy.start()
        self.dispatch_event = event_dispatcher(config)
        self.config = config
        self.disconnect = proxy.stop


def create_shell():
    with open('config.yml') as fle:
        config = yaml.load(fle, Loader=yaml.FullLoader)

    banner = f'Nameko Python {sys.version}\nBroker is {config[AMQP_URI_CONFIG_KEY]}'
    n = make_nameko_helper(config)
    ctx = {'n': n, 'rpc': n.rpc, 'config': config}
    ctx['authed'] = ShellHelper(config, context_data={'miso_auth_token': 'bleh'})
    runner = ShellRunner(banner, ctx)
    runner.start_shell(name=None)


if __name__ == '__main__':
    register_better_json()
    create_shell()
