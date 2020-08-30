from nameko.rpc import RpcProxy
from miso.service import Service, rpc_enhanced


class AuthExampleService(Service):
    name = 'auth_examples'
    proxy_self = RpcProxy('auth_examples2')

    @rpc_enhanced(require_auth=True)
    def confirm_authenticated(self):
        return 'You are authenticated'

    @rpc_enhanced(require_tenant=['testing', 'c3group'])
    def confirm_tenant(self):
        return 'You are of the tenant we expect'

    @rpc_enhanced(require_role=['system', 'execute'])
    def confirm_role(self):
        return 'You have the appropriate roles'

    @rpc_enhanced(sudo='testing')
    def sudo_whoami(self):
        return self.auth.whoami()

    @rpc_enhanced
    def whoami(self):
        return self.auth.whoami()


class AuthExampleService2(Service):
    name = 'auth_examples2'

    @rpc_enhanced
    def whoami(self):
        return self.auth.whoami()
