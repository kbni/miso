from miso.service import Service, http_enhanced
from miso.utils import hostname


class HttpExampleService(Service):
    name = 'http_example'

    @http_enhanced('GET', '/hostname', force_res_object=True)
    def hostname(self, request):
        return self.new_result(hostname())

    @http_enhanced('GET', '/hostname_full', require_auth=True)
    def hostname_full(self, request):
        return self.new_result(hostname(short=False))
