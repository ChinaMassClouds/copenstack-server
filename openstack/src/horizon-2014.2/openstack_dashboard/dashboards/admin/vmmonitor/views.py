from horizon import tables
from openstack_dashboard.dashboards.admin.vmmonitor import tables as vmmonitor_tables
from openstack_dashboard.openstack.common.requestapi import RequestApi
from openstack_dashboard.openstack.common.dictutils import DictList2ObjectList
from horizon import exceptions
from django.utils.translation import ugettext_lazy as _

class IndexView(tables.MultiTableView):
    template_name = 'admin/vmmonitor/index.html'
    table_classes = (vmmonitor_tables.VmAlarmTable,
                     vmmonitor_tables.VmPolicyTable)
    
    def get_vm_alarm_data(self):
        return DictList2ObjectList([{'vm_name':'vm_name',
                                     'alarm_content':'alarm_content',
                                     'status':'status'
                                     }])
        
    def get_vm_policy_data(self):
        return DictList2ObjectList([{'name':'name',
                                     'data_center':'data_center',
                                     'status':'new'
                                     }])
