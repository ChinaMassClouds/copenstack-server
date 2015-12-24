from horizon import tables
from openstack_dashboard.dashboards.admin.hostmonitor import tables as hostmonitor_tables
from openstack_dashboard.openstack.common.requestapi import RequestApi
from openstack_dashboard.openstack.common.dictutils import DictList2ObjectList
from horizon import exceptions
from django.utils.translation import ugettext_lazy as _

class IndexView(tables.MultiTableView):
    template_name = 'admin/hostmonitor/index.html'
    table_classes = (hostmonitor_tables.HostAlarmTable,
                     hostmonitor_tables.HostPolicyTable)
    
    def get_host_alarm_data(self):
        return DictList2ObjectList([{'host_name':'host_name',
                                     'alarm_content':'alarm_content',
                                     'status':'status'
                                     }])
        
    def get_host_policy_data(self):
        return DictList2ObjectList([{'name':'name',
                                     'data_center':'data_center',
                                     'status':'new'
                                     }])
