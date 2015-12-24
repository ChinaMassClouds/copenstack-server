from openstack_dashboard.dashboards.admin.alarmpolicy import tables as alarmpolicy_tables
from openstack_dashboard.dashboards.admin.alarmpolicy import workflows as alarmpolicy_workflows
from openstack_dashboard.dashboards.admin.alarmpolicy import forms as alarmpolicy_forms
from horizon import tables
from horizon import forms
from horizon import workflows
from openstack_dashboard.models import alarmpolicy
from django.utils.translation import ugettext_lazy as _
from openstack_dashboard.openstack.common.dictutils import DictList2ObjectList
import openstack_dashboard.openstack.common.configparser_tool as cfg_tool
import enum 
import os
import ConfigParser
import json
import base64
from django.core.urlresolvers import reverse_lazy

class IndexView(tables.MultiTableView):
    template_name = 'admin/alarmpolicy/index.html'
    table_classes = (alarmpolicy_tables.AlarmPolicyTable,
                     alarmpolicy_tables.EmailReceiverTable)
    
    def get_emailreceiver_data(self):
        if os.path.exists(enum.EMAIL_CFG_FILE):
            cfgparser = ConfigParser.ConfigParser()
            cfgparser.read(enum.EMAIL_CFG_FILE)
            receiver = cfg_tool.getOption(cfgparser, 'receiver', 'receiver')

            res = []
            if receiver:
                for a in json.loads(receiver):
                    res.append({'address':a})
                return DictList2ObjectList(res,'address')
        return []
    
    def get_alarmpolicy_data(self):
        policy_data = alarmpolicy.objects.all().order_by('id')
        index = 1
        for p in policy_data:
            p.policy_content = self.getPolicyContent(p)
            p.status = self.translateStatus(p.enabled)
            p.alarm_way = self.translateAlarmWay(p.alarm_way)
            p.type = self.translateSourceType(p.type)
            p.order_number = index
            index = index + 1
        return policy_data
    
    def translateSourceType(self,source_type):
        for i in enum.SOURCE_TYPE_LIST:
            if source_type == i[0]:
                return i[1]
        return ''
    
    def getPolicyContent(self,obj):
        content = ''
        param = []
        if obj.cpu_threshold:
            s = str(obj.cpu_threshold)
            content += 'CPU > %s'
            param.append(s + '%')
        if obj.mem_threshold:
            if content:
                content += ' or '
            s = str(obj.mem_threshold)
            content += 'Mem > %s'
            param.append(s + '%')
        if obj.disk_threshold:
            if content:
                content += ' or '
            s = str(obj.disk_threshold)
            content += 'Disk > %s'
            param.append(s + '%')
        if content:
            s = str(obj.duration)
            content += '; duration %s minutes'
            param.append(s)
        if content:
            return _(content) % tuple(param)
        else:
            return ''
    
    def translateStatus(self,enabled):
        if enabled:
            return _('Enable')
        else:
            return _('Not Enabled')
    
    def translateAlarmWay(self,alarm_way):
        if alarm_way == enum.EMAIL_ALARM_VALUE:
            return _('Alarm with email')
        else:
            return alarm_way

class AddPolicyView(workflows.WorkflowView):
    workflow_class = alarmpolicy_workflows.AddPolicyWorkflow
    template_name = 'admin/alarmpolicy/add_policy.html'
    
class SetMailView(forms.ModalFormView):
    template_name = 'admin/alarmpolicy/set_mail.html'
    form_class = alarmpolicy_forms.SetMailForm
    success_url = reverse_lazy('horizon:admin:alarmpolicy:index')

    def get_initial(self):
        if os.path.exists(enum.EMAIL_CFG_FILE):
            cfgparser = ConfigParser.ConfigParser()
            cfgparser.read(enum.EMAIL_CFG_FILE)

        return {'server_address':cfg_tool.getOption(cfgparser, 'server', 'ipaddress'),
                'server_port':cfg_tool.getOption(cfgparser, 'server', 'port'),
                'sender_address':cfg_tool.getOption(cfgparser, 'sender', 'address'),
                'sender_username':cfg_tool.getOption(cfgparser, 'sender', 'user'),
                'old_password':cfg_tool.getOption(cfgparser, 'sender', 'password')}
        
class AddReceiverView(forms.ModalFormView):
    template_name = 'admin/alarmpolicy/add_receiver.html'
    form_class = alarmpolicy_forms.AddReceiverForm
    success_url = reverse_lazy('horizon:admin:alarmpolicy:index')

