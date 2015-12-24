from horizon import tables
from django.utils.translation import ugettext_lazy as _
from openstack_dashboard.models import alarmpolicy
from openstack_dashboard.openstack.common.log import operate_log
from openstack_dashboard import api
from horizon import exceptions
import openstack_dashboard.openstack.common.configparser_tool as cfg_tool
import json
import ConfigParser
import enum

class AddPolicyAction(tables.LinkAction):
    name = "addpolicy"
    verbose_name = _("Add Policy")
    url = "horizon:admin:alarmpolicy:addpolicy"
    classes = ("ajax-modal", )
    icon = "plus"


class SetMailAction(tables.LinkAction):
    name = "setmail"
    verbose_name = _("Mail Settings")
    url = "horizon:admin:alarmpolicy:setmail"
    classes = ("ajax-modal", )


class AddReceiverAction(tables.LinkAction):
    name = "addreceiver"
    verbose_name = _("Add mail receiver")
    url = "horizon:admin:alarmpolicy:addreceiver"
    classes = ("ajax-modal", )
    icon = 'plus'


class EnableAction(tables.BatchAction):
    name = "enable"
    
    @staticmethod
    def action_present(count):
        return _("Enable")

    @staticmethod
    def action_past(count):
        return _("Enable")
        
    def allowed(self, request, datum):
        return not datum.enabled
    
    def action(self, request, obj_id):
        try:
            policy_obj = alarmpolicy.objects.get(id=obj_id)
            policys_id = getattr(policy_obj,'policys_id','')
            if policys_id:
                policys_arr = policys_id.split(',')
                for p_id in policys_arr:
                    ceilometer_policy = api.ceilometer.get_alarm(request,p_id)
                    ceilometer_policy.enabled = True
                    api.ceilometer.update_alarm(request,ceilometer_policy)
            policy_obj.enabled = True
            policy_obj.save()
            operate_log(request.user.username,
                            request.user.roles,
                            "\"" + getattr(policy_obj,'name','') + "\" alarm-policy enable success")
        except Exception as e:
            operate_log(request.user.username,
                            request.user.roles,
                            "\"" + getattr(policy_obj,'name','') + "\" alarm-policy enable error")
            exceptions.handle(request,
                              _('Unable to enable the policy.'))
            
class DelReceiverAction(tables.DeleteAction):
    name = "delreceiver"
    
    @staticmethod
    def action_present(count):
        return _("Delete")

    @staticmethod
    def action_past(count):
        return _("Delete")
    
    def action(self, request, obj_id):
        try:
            cfgparser = ConfigParser.ConfigParser()
            cfgparser.read(enum.EMAIL_CFG_FILE)
            receiver = cfg_tool.getOption(cfgparser, 'receiver', 'receiver')
            if receiver:
                arr = json.loads(receiver)
                arr.remove(obj_id)
            cfg_tool.setOption(cfgparser, 'receiver', 'receiver', json.dumps(arr))
            cfgparser.write(open(enum.EMAIL_CFG_FILE,'w'))
            operate_log(request.user.username,
                        request.user.roles,
                        "delete mail-receiver \"" + obj_id + "\" success")
        except Exception as e:
            operate_log(request.user.username,
                        request.user.roles,
                        "delete mail-receiver \"" + obj_id + "\" error")


class DisableAction(tables.BatchAction):
    name = "disable"

    @staticmethod
    def action_present(count):
        return _("disabled")

    @staticmethod
    def action_past(count):
        return _("disabled")
        
    def allowed(self, request, datum):
        return datum.enabled
    
    def action(self, request, obj_id):
        try:
            policy_obj = alarmpolicy.objects.get(id=obj_id)
            policys_id = getattr(policy_obj,'policys_id','')
            if policys_id:
                policys_arr = policys_id.split(',')
                for p_id in policys_arr:
                    ceilometer_policy = api.ceilometer.get_alarm(request,p_id)
                    ceilometer_policy.enabled = False
                    api.ceilometer.update_alarm(request,ceilometer_policy)
            policy_obj.enabled = False
            policy_obj.save()
            operate_log(request.user.username,
                            request.user.roles,
                            "\"" + getattr(policy_obj,'name','') + "\" alarm-policy disable success")
        except Exception as e:
            operate_log(request.user.username,
                            request.user.roles,
                            "\"" + getattr(policy_obj,'name','') + "\" alarm-policy disable error")
    
class DeleteAction(tables.DeleteAction):
    name = "delete"
    
    @staticmethod
    def action_present(count):
        return _("Delete")

    @staticmethod
    def action_past(count):
        return _("Delete")
    
    def action(self, request, obj_id):
        try:
            alarmpolicy_data = alarmpolicy.objects.get(id=obj_id)
            policys_id = getattr(alarmpolicy_data,'policys_id','')
            if policys_id:
                policys_arr = policys_id.split(',')
                for p_id in policys_arr:
                    api.ceilometer.delete_alarm(request,p_id)
            alarmpolicy_data.delete()
            operate_log(request.user.username,
                            request.user.roles,
                            "\"" + getattr(alarmpolicy_data,'name','') + "\" alarm-policy delete success")
        except Exception as e:
            operate_log(request.user.username,
                            request.user.roles,
                            "\"" + getattr(alarmpolicy_data,'name','') + "\" alarm-policy delete error")
    
class AlarmPolicyTable(tables.DataTable):
    order_number = tables.Column("order_number",verbose_name=_("Order Number"))
    name = tables.Column("name",verbose_name=_("Name"))
    source_type = tables.Column("type",verbose_name=_("Source Type"))
    hosts_name = tables.Column("hosts_name",verbose_name=_("Target hosts/vms"))
    policy_content = tables.Column("policy_content",verbose_name=_("Policy Content"))
    status = tables.Column("status",verbose_name=_("Status"))
    alarm_way = tables.Column("alarm_way",verbose_name=_("Alarm Way"))
    
    class Meta:
        name = "alarmpolicy"
        verbose_name = _("Alarm Policy")
        table_actions = (AddPolicyAction,)
        row_actions = (EnableAction,DisableAction,DeleteAction)
        
class EmailReceiverTable(tables.DataTable):
    address = tables.Column("address",verbose_name=_("Receiver Mail Address"))
    
    class Meta:
        name = "emailreceiver"
        verbose_name = _("Mail Settings")
        table_actions = (SetMailAction,AddReceiverAction)
        row_actions = (DelReceiverAction,)
