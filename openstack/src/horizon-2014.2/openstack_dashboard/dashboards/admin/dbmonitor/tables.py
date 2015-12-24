from horizon import tables
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext_lazy

class ConfirmAction(tables.LinkAction):
    name = "editpolicy"
    verbose_name = _("Confirm Alarm")
    url = '/test'
    
class EditPolicyAction(tables.LinkAction):
    name = "editpolicy"
    verbose_name = _("Edit")
    url = '/test'
    icon = 'pencil'
    
class AddPolicyAction(tables.LinkAction):
    name = "addpolicy"
    verbose_name = _("Add Alarm Policy")
    url = '/test'
    icon = 'plus'

class DelPolicyAction(tables.DeleteAction):
    @staticmethod
    def action_present(count):
        return _("Delete")

    @staticmethod
    def action_past(count):
        return ungettext_lazy(
            u"Deleted Source Domain",
            u"Deleted Source Domains",
            count
        )

    def delete(self, request, obj_id):
        pass

class DbPolicyTable(tables.DataTable):
    name = tables.Column("name",verbose_name=_("Name"))
    data_center = tables.Column("data_center",verbose_name=_("Data Center"))
    status = tables.Column("status",verbose_name=_("Status"))
    
    class Meta:
        name = "db_policy"
        verbose_name = _("Alarm Policy")
        table_actions = (EditPolicyAction,AddPolicyAction,DelPolicyAction)

class DbAlarmTable(tables.DataTable):
    host_name = tables.Column("host_name",verbose_name=_("Alarm Host"))
    alarm_content = tables.Column("alarm_content",verbose_name=_("Alarm Content"))
    status = tables.Column("status",verbose_name=_("Status"))
    
    class Meta:
        name = "db_alarm"
        verbose_name = _("Alarm Info")
        table_actions = (ConfirmAction,)
        