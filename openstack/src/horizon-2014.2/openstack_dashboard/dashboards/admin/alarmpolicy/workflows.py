import json
import logging
import enum

from django.utils.translation import ugettext_lazy as _
from horizon import forms
from horizon import workflows
from openstack_dashboard import api
from openstack_dashboard.models import alarmpolicy
from openstack_dashboard.openstack.common.log import operate_log
from horizon import exceptions
from openstack_dashboard.openstack.common.requestapi import RequestApi
from openstack_dashboard.openstack.common.base import f_getIpByHostname

LOG = logging.getLogger(__name__)
g_allHostsAndVms = []

def allPolicyedHostsVms():
    all = alarmpolicy.objects.all()
    policyed = []
    for a in all:
        if a.hosts_id:
            policyed = policyed + a.hosts_id.split(',')
    return policyed

def getAvailableHostsAndVms(request):
    res = []
    allpolicyedhostsvms = allPolicyedHostsVms()
    zones = api.nova.aggregate_details_list(request)
    
    try:
        request_api = RequestApi()
        hosts2 = request_api.getRequestInfo('api/heterogeneous/platforms/hosts') or []

    except Exception:
        hosts2 = []
        exceptions.handle(request,
                          _('Unable to retrieve hosts list.'))
    
    for z in zones:
        if z.hosts:
            zone_hosts = [f_getIpByHostname(h) for h in z.hosts]
            for h in zone_hosts + [h.get('address') for h in hosts2 if h.get('domain') == z.availability_zone]:
                if h not in allpolicyedhostsvms:
                    res.append({'zone':z.availability_zone,
                                'type':'host',
                                'id':h,
                                'name':h})
                
    instances,_more = api.nova.server_list(
            request,
            all_tenants=True)
    for i in instances:
        if getattr(i,'id','') not in allpolicyedhostsvms:
            res.append({'zone':getattr(i,'OS-EXT-AZ:availability_zone',''),
                        'type':'vm',
                        'id':getattr(i,'id',''),
                        'name':getattr(i,'name','')})
    res = sorted(res, key = lambda n:n.get('name'))
    return res

class PolicyBaseInfoAction(workflows.Action):
    allHostsAndVms = forms.CharField(widget=forms.HiddenInput(),required=False)
    
    name = forms.CharField(max_length=100, label=_("Name"))
    zone = forms.ChoiceField(label=_("Belonged Source Domain"))
    source_type = forms.ChoiceField(label=_("Source Type"),
                                    choices=enum.SOURCE_TYPE_LIST)
    
    class Meta:
        name = _("Name")
        help_text = _("Input the policy name, select the domain of target hosts or vms.")
        slug = "policy_base_info"
        
    def __init__(self, request, *args, **kwargs):
        super(PolicyBaseInfoAction, self).__init__(request, *args, **kwargs)
        global g_allHostsAndVms
        all_hosts_and_vms = getAvailableHostsAndVms(request)
        g_allHostsAndVms = all_hosts_and_vms
        self.fields['allHostsAndVms'].initial = json.dumps(all_hosts_and_vms)
        
    def populate_zone_choices(self, request, initial):
        res = []
        zones = api.nova.aggregate_details_list(self.request)
        zones = sorted(zones,key=lambda n:n.name)
        for z in zones:
            res.append((z.availability_zone,z.availability_zone))
        return res
        
    def clean(self):
        cleaned_data = super(PolicyBaseInfoAction, self).clean()
        exists_policys = alarmpolicy.objects.all()
        for p in exists_policys:
            if p.name == cleaned_data.get('name'):
                raise forms.ValidationError(
                        _('The name "%s" is already used by another policy.')
                        % cleaned_data.get('name')
                    )
        return cleaned_data

class PolicyTargetAction(workflows.MembershipAction):
    def __init__(self, request, *args, **kwargs):
        super(PolicyTargetAction, self).__init__(request,
                                                        *args,
                                                        **kwargs)
        err_msg = _('Unable to get the available hosts/vms')

        default_role_field_name = self.get_default_role_field_name()
        self.fields[default_role_field_name] = forms.CharField(required=False)
        self.fields[default_role_field_name].initial = 'member'

        field_name = self.get_member_field_name('member')
        self.fields[field_name] = forms.MultipleChoiceField(required=False)

        hosts = g_allHostsAndVms
        choices = []
        for h in hosts:
            choices.append((h.get('id'),h.get('name')))
        self.fields[field_name].choices = choices
        
    class Meta:
        name = _("Target hosts/vms")
        slug = "target"
    
class PolicyPointAction(workflows.Action):
    cpu_point = forms.IntegerField(label=_("CPU alarm point (%)"),
                                   min_value=1,max_value=99,
                                   initial = 50,
                                   required=False)
    mem_point = forms.IntegerField(label=_("Memory alarm point (%)"),
                                   min_value=1,max_value=99,
                                   initial = 50,
                                   required=False)
    disk_point = forms.IntegerField(label=_("Disk alarm point (%)"),
                                    min_value=1,max_value=99,
                                    initial = 50,
                                    required=False)
    
    class Meta:
        name = _("Rule")
        help_text = _('If the utilization larger than the setted points, the system will alarm.')
        slug = "policy_point"
        
    def __init__(self, request, *args, **kwargs):
        super(PolicyPointAction, self).__init__(request, *args, **kwargs)

    def clean(self):
        cleaned_data = super(PolicyPointAction, self).clean()
        return cleaned_data
    
class PolicyAlarmAction(workflows.Action):
    duration = forms.IntegerField(min_value=1,max_value=9999, 
                                initial = 5,
                                label=_("Duration (min)"))
    email_alarm = forms.BooleanField(label=_("Email Alarm"),
                                   widget=forms.CheckboxInput,
                                   initial=True,
                                   required=False)
    
    class Meta:
        name = _("Duration")
        help_text = _("In case the usage of resource lager than the setted threshold and keeps a long time, "
                      "system will alarm, you can set using email or not.")
        slug = "policy_alarm"
        
    def __init__(self, request, *args, **kwargs):
        super(PolicyAlarmAction, self).__init__(request, *args, **kwargs)

    def clean(self):
        cleaned_data = super(PolicyAlarmAction, self).clean()
        return cleaned_data
    
class PolicyBaseInfoStep(workflows.Step):
    action_class = PolicyBaseInfoAction
    contributes = ("name","zone",
                   "source_type")
    
class PolicyTargetStep(workflows.UpdateMembersStep):
    action_class = PolicyTargetAction
    help_text = ''
    available_list_title = _("All available hosts or vms")
    members_list_title = _("Selected hosts or vms")
    no_available_text = _("No hosts or vms found.")
    no_members_text = _("No host or vm selected.")
    show_roles = False
    contributes = ("hosts",)
    
    def contribute(self, data, context):
        if data:
            member_field_name = self.get_member_field_name('member')
            context['hosts'] = data.get(member_field_name, [])
        return context
    
class PolicyPointStep(workflows.Step):
    action_class = PolicyPointAction
    contributes = ("cpu_point",
                   "mem_point")
    
class PolicyAlarmStep(workflows.Step):
    action_class = PolicyAlarmAction
    contributes = ("duration",
                   "email_alarm")
    
class AddPolicyWorkflow(workflows.Workflow):
    slug = "add_alarm_policy"
    name = _("Add Alarm Policy")
    finalize_button_name = _("Add")
    failure_message = _('Unable to add alarm policy "%s".')
    success_url = 'horizon:admin:alarmpolicy:index'
    default_steps = (PolicyBaseInfoStep, PolicyTargetStep, PolicyPointStep, PolicyAlarmStep)
    wizard = True

    def handle(self, request, context):
        try:
            hosts_id = ''
            hosts_name = ''
            for i in context.get('hosts'):
                if hosts_id:
                    hosts_id += ','
                    hosts_name += ','
                hosts_id += i
                hosts_name += self.getTargetsNameById(context.get('zone'), context.get('source_type'), i)
            policys_id = self.createCeilometerAlarm(context)
            if not policys_id:
                operate_log(request.user.username,
                            request.user.roles,
                            "\"" + context.get('name') + "\" alarm-policy create error")
                return False
            policy_model = alarmpolicy(name = context.get('name'),
                    type = context.get('source_type'),
                    zone = context.get('zone'),
                    hosts_id = hosts_id,
                    hosts_name = hosts_name,
                    cpu_threshold = int(context.get('cpu_point') or '0'),
                    mem_threshold = int(context.get('mem_point') or '0'),
                    disk_threshold = int(context.get('disk_point') or '0'),
                    duration = int(context.get('duration') or '0'),
                    alarm_way = enum.EMAIL_ALARM_VALUE if context.get('email_alarm') else '',
                    enabled = False,
                    policys_id = policys_id,
                    create_user = request.user.username,
                    create_date = None)
            policy_model.save()
            operate_log(request.user.username,
                            request.user.roles,
                            "\"" + context.get('name') + "\" alarm-policy create success")
            return True
        except Exception as e:
            operate_log(request.user.username,
                            request.user.roles,
                            "\"" + context.get('name') + "\" alarm-policy create error")
            return False
    
    def getTargetsNameById(self,zone,type,id):
        for t in g_allHostsAndVms:
            if t.get('zone') == zone \
                    and t.get('type') == type \
                    and t.get('id') == id:
                return t.get('name')
        return ''
    
    def createCeilometerAlarm(self, policy_obj):
        hosts_arr = policy_obj.get('hosts')

        policys_id = ''
        def set_policys_id(policys_id,policy_id):
            if policys_id:
                policys_id += ',' 
            policys_id += policy_id
            return policys_id
        for host_id in hosts_arr:
            if policy_obj.get('cpu_point'):
                param1 = self.getParamForCreateAlarm(policy_obj,host_id,'cpu')
                if not param1:
                    return ''
                res1 = api.ceilometer.create_alarm(self.request, param1)
                policy_id = getattr(res1,'alarm_id','')
                policys_id = set_policys_id(policys_id,policy_id)
            if policy_obj.get('mem_point'):
                param2 = self.getParamForCreateAlarm(policy_obj, host_id,'mem')
                if not param2:
                    return ''
                res2 = api.ceilometer.create_alarm(self.request,param2)
                policy_id = getattr(res2,'alarm_id','')
                policys_id = set_policys_id(policys_id,policy_id)
            if policy_obj.get('disk_point'):
                param3 = self.getParamForCreateAlarm(policy_obj, host_id,'disk')
                if not param3:
                    return ''
                res3 = api.ceilometer.create_alarm(self.request,param3)
                policy_id = getattr(res3,'alarm_id','')
                policys_id = set_policys_id(policys_id,policy_id)

        return policys_id

            
    def getParamForCreateAlarm(self,policy_obj,host_id,flag):
        meter_name = ''
        threshold_name = ''
        if flag == 'cpu':
            meter_name = 'cpu_util' if policy_obj.get('source_type') == 'vm' else 'hardware.cpu.load.1min'
            threshold_name = 'cpu_point'
        elif flag == 'mem':
            meter_name = 'memory.usage' if policy_obj.get('source_type') == 'vm' else 'hardware.memory.used'
            threshold_name = 'mem_point'
        elif flag == 'disk':
            meter_name = 'aaa' if policy_obj.get('source_type') == 'vm' else 'hardware.disk.size.used'
            threshold_name = 'disk_point'

        if not meter_name or not threshold_name:
            return None

        param = {'type':'threshold','enabled':False}
        param['name'] = policy_obj.get('name') + '_' + host_id + '_' + meter_name
        
        
        if bool(policy_obj.get('email_alarm')):
            param['alarm_actions'] = ['log://']
        else:
            param['alarm_actions'] = []
        
        threshold_rule = {'meter_name':meter_name,
                          'period':int(policy_obj.get('duration')) * 60,
                          'comparison_operator':'gt',
                          'query': [{
                                    "field": "resource_id",
                                    "op": "eq",
                                    "type": "",
                                    "value": host_id}],
                          'threshold':float(policy_obj.get(threshold_name))}

        param['threshold_rule'] = threshold_rule
        return param