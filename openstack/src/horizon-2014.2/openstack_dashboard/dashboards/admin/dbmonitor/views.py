from horizon import tables
from openstack_dashboard.dashboards.admin.dbmonitor import tables as dbmonitor_tables
from openstack_dashboard.openstack.common.requestapi import RequestApi
from openstack_dashboard.openstack.common.dictutils import DictList2ObjectList
from horizon import exceptions
from django.utils.translation import ugettext_lazy as _

class IndexView(tables.MultiTableView):
    template_name = 'admin/dbmonitor/index.html'
    table_classes = (dbmonitor_tables.DbAlarmTable,
                     dbmonitor_tables.DbPolicyTable)
    
    def get_db_alarm_data(self):
        return DictList2ObjectList([{'host_name':'host_name',
                                     'alarm_content':'alarm_content',
                                     'status':'status'
                                     }])
        
    def get_db_policy_data(self):
        return DictList2ObjectList([{'name':'name',
                                     'data_center':'data_center',
                                     'status':'new'
                                     }])
