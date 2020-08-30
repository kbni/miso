import datetime
from miso.service import Service, rpc_enhanced


class ResultExamples(Service):
    name = 'result_examples'

    @rpc_enhanced
    def confirm_result(self, x, y, res):
        actual = int(x) * int(y)
        if actual == res:
            return self.new_result(result=True, data=f'{x}*{y} does equal {res}')
        else:
            return self.new_result(result=False, data=f'{x}*{y} does not equal {res}')

    @rpc_enhanced
    def get_datetime(self):
        return datetime.datetime.utcnow()

    @rpc_enhanced(force_res_object=False)
    def get_result_noauto(self, from_input):
        return from_input
    
    @rpc_enhanced()
    def get_result_auto(self, from_input):
        return from_input
