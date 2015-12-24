from horizon import tables
from openstack_dashboard.dashboards.admin.alarmmsg import tables as alarmmsg_tables
from openstack_dashboard.openstack.common.dictutils import DictList2ObjectList
from openstack_dashboard import api
from openstack_dashboard.models import alarmpolicy,treatedalarm
from django.utils.translation import ugettext_lazy as _
import json
import enum
from horizon import exceptions
import logging

LOG = logging.getLogger(__name__)

class IndexView(tables.DataTableView):
    template_name = 'admin/alarmmsg/index.html'
    table_class = alarmmsg_tables.AlarmmsgTable
    
    def get_data(self):
        try:
            res = []
            policy_list = alarmpolicy.objects.all()
            treatedalarms = self.getTreatedAlarms()
            for policy in policy_list:
                alarms_id = getattr(policy,'policys_id','')
                if alarms_id:
                    for alarm_id in alarms_id.split(','):
                        hist_list = api.ceilometer.get_alarm_hist(self.request,alarm_id)
                        if hist_list:
                            for hist in hist_list:
                                if hist.detail and json.loads(hist.detail).get('state') == 'alarm':
                                    alarm = api.ceilometer.get_alarm(self.request,alarm_id)
                                    threshold_rule = alarm.threshold_rule
                                    vm_id = threshold_rule.get('query')[0].get('value')
                                    vm_name = ''
                                    hosts_id_arr = getattr(policy,'hosts_id','').split(',')
                                    hosts_name_arr = getattr(policy,'hosts_name','').split(',')
                                    for i in range(len(hosts_id_arr)):
                                        if hosts_id_arr[i] == vm_id:
                                            vm_name = hosts_name_arr[i]
                                    
                                    status_code = 'treated' if hist.event_id in treatedalarms else 'untreated'
                                    res.append({'id':hist.event_id,
                                                'alarm_content':self.getAlarmContent(threshold_rule),
                                                'source_type':self.translateSourceType(policy.type) ,
                                                'zone':policy.zone,
                                                'status':self.translateStatus(status_code),
                                                'status_code':status_code,
                                                'timestamp':hist.timestamp[0:19].replace('T',' ')
                                                        if hist.timestamp and len(hist.timestamp) >= 19 
                                                        else '',
                                                'name':vm_name})
            res = self.filter_data(res)
            res.sort(cmp = lambda x,y : cmp(y.get('timestamp') , x.get('timestamp')))
            index = 1
            for i in res:
                i['order_number'] = index
                index += 1
            return DictList2ObjectList(res)
        except Exception as e:
            exceptions.handle(self.request,
                              _('Unable to retrieve alarm messages list.'))
            return []
    
    def getTreatedAlarms(self):
        list = treatedalarm.objects.all()
        return [md.event_id for md in list]
    
    def translateSourceType(self,source_type):
        for i in enum.SOURCE_TYPE_LIST:
            if source_type == i[0]:
                return i[1]
        return ''
    
    def translateStatus(self,status):
        for i in enum.TREATED_OR_NOT:
            if status == i[0]:
                return i[1]
        return ''
    
    def getAlarmContent(self,threshold_rule):
        meter_name = threshold_rule.get('meter_name')
        threshold = threshold_rule.get('threshold')
        period = threshold_rule.get('period')
        meter = ''
        if meter_name in ['cpu_util','hardware.cpu.load.1min']:
            meter = 'cpu'
        elif meter_name in ['memory.usage','hardware.memory.used']:
            meter = 'mem'
        elif meter_name in ['hardware.disk.size.used']:
            meter = 'disk'
        content = meter + ' used larger than %s keep more than %s minutes' 
        return _(content) % (str(threshold) + '%',period / 60 )
    
    def get_filters(self):
        filters = {}
        filter_field = self.table.get_filter_field()
        filter_string = self.table.get_filter_string()
        filter_action = self.table._meta._filter_action
        if filter_field and filter_string :
            filters[filter_field] = filter_string
        return filters

    def filter_data(self, data):
        filters = self.get_filters()

        res_data = []
        if not filters.keys():
            return data
        for d in data:
            for key in filters.keys():
                if key == 'name' and filters[key]:
                    if filters[key] in d.get('name'):
                        res_data.append(d)
                elif key == 'source_type' and filters[key]:
                    if filters[key] == d.get('source_type'):
                        res_data.append(d)
                elif key == 'zone' and filters[key]:
                    if filters[key] == d.get('zone'):
                        res_data.append(d)
                elif key == 'status' and filters[key]:
                    if filters[key] == d.get('status'):
                        res_data.append(d)
        return res_data
    