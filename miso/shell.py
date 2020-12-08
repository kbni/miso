import os
import sys
import yaml
import json

from logging import getLogger
from envyaml import EnvYAML
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


def create_shell(with_files, exit_after=False):
    config = dict(**EnvYAML('config.yml'))
    banner = f'Nameko Python {sys.version}\nBroker is {config[AMQP_URI_CONFIG_KEY]}'
    n = make_nameko_helper(config)
    ctx = {'n': n, 'rpc': n.rpc, 'config': config, 'os': os, 'sys': sys, 'json': json, 'yaml': yaml}
    ctx['authed'] = ShellHelper(config, context_data={'miso_auth_token': 'bleh'})
    for fn in with_files:
        with open(fn, 'r') as fh:
            print(f'executing {fn}')
            exec(fh.read(), ctx)
    if not exit_after:
        runner = ShellRunner(banner, ctx)
        runner.start_shell(name=None)


if __name__ == '__main__':
    register_better_json()
    exit_after = False
    with_files = []
    for arg in sys.argv[1:]:
        if arg in ('-e', '--exit'):
            exit_after = True
        elif os.path.exists(arg):
            with_files.append(arg)
        else:
            sys.stderr.write(f"Bad argument or file does not exist: {arg}")
            sys.exit(1)
    create_shell(with_files, exit_after)
