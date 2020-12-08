import os
import time
import json
from logging import getLogger
from nameko.web.handlers import http
from werkzeug.wrappers import Response

from nameko.standalone.rpc import ClusterRpcProxy
from nameko.rpc import RpcProxy

from miso.service import http_enhanced, rpc_enhanced, Service

fake_proxy_config = {
    'AMQP_URI': os.environ.get('NAMEKO_AMQP_URL'),
    'serializer': 'betterjson'
}


class ConfirmService(Service):
    name = "confirm"

    @http_enhanced('GET', '/confirm/available')
    def get_available(self, request, job_guid):
        return 200, f"{self.name} service is available"
