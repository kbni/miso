import os
import json

from nameko.standalone.rpc import ClusterRpcProxy
from nameko.rpc import RpcProxy

from miso.service import http_enhanced, rpc_enhanced, Service
from miso.utils import fake_proxy_config, epoch



class HttpService(Service):
    name = "flowtasks"
    myself = RpcProxy('flowtasks')

    @rpc_enhanced(force_res_object=False)
    def update_keys(self, perm_json):
        self.logger.warning('Updated flow_tasks:permissions -> %s', perm_json)
        self.redis.setj('flow_tasks:permissions', perm_json)
        return True

    @rpc_enhanced(force_res_object=False)
    def verify_key(self, key, desired_service, desired_method):
        perms = self.redis.getj('flow_tasks:permissions')
        success = False
        result = 'failed: no matching permissions'

        if not isinstance(perms, dict):
            result = 'failed: permissions are missing'
        elif key not in perms:
            result = 'failed: invalid key'
        else:
            result = 'failed: permissions inadequate'
            for test_value in ('*.*', f'{desired_service}.*', f'{desired_service}.{desired_method}'):
                if test_value in perms[key]:
                    success = True
                    result = f'success: matched {test_value}'
                    break

        self.logger.info('checking key [%s] against [%s.%s] %s', key, desired_service, desired_method, result)
        return success

    @rpc_enhanced
    def invoke_rpc(self, result_key, service, method, *args, **kwargs):
        self.logger.info('invoking [%s.%s] and storing result at [%s]', service, method, result_key)
        with ClusterRpcProxy(fake_proxy_config()) as cluster_rpc:
            func = getattr(getattr(cluster_rpc, service), method)
            result = func(*args, **kwargs)
            if hasattr(result, 'to_dict'):
                result = result.to_dict()
            self.redis.setj(result_key+':result', result)
            self.redis.setj(result_key+':when', epoch())
            self.redis.expire(result_key, 3600*24*2)
            self.redis.expire(result_key+':when', 3600*24*2)

    @http_enhanced('GET', '/flow_tasks/available')
    def get_available(self, request, job_guid):
        return 200, "service is available"

    @http_enhanced('POST', '/flow_tasks/<string:job_guid>')
    def trigger_job(self, request, job_guid):
        req_body = request.get_data(as_text=True)
        if 'service' not in req_body and 'auth' not in req_body:
            return 401, 'sorry, not sorry.'
        try:
            self.logger.info('req_body = %s', req_body[:90])
            req_json = json.loads(req_body)
        except Exception as e:
            self.logger.error(e, exc_info=True)
            return 401, 'sorry, not sorry.'

        auth = req_json.get('auth', None)
        service = req_json.get('service', None)
        args = req_json.get('args', [])
        kwargs = req_json.get('kwargs', {})

        if not auth or not service or not isinstance(args, list) or not isinstance(kwargs, dict):
            return 500, 'bad request'

        desired_service, desired_method = service.split('.', 1)
        if not self.verify_key(auth, desired_service, desired_method):
            return 403, 'invalid key'

        key = f'flow_tasks:tasks:{job_guid}'
        self.myself.invoke_rpc.call_async(key, desired_service, desired_method, *args, **kwargs)
        return 202, 'job running'

    @http_enhanced('GET', '/flow_tasks/<string:job_guid>')
    def check_job(self, request, job_guid):
        key = f'flow_tasks:tasks:{job_guid}:result'
        task_result = self.redis.getj(key)
        self.logger.info('looking for job with guid: %s returned %s', job_guid, task_result)

        if task_result:
            return 200, task_result
        else:
            return 404, {'reason': 'no data for that guid'}

