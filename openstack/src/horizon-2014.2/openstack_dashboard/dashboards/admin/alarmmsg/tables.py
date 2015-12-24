from horizon import tables
from django.utils.translation import ugettext_lazy as _
from horizon import exceptions
from openstack_dashboard.models import treatedalarm
from openstack_dashboard.openstack.common.log import operate_log

class AlarmmsgFilterAction(tables.FilterAction):
    filter_type = "server"
    filter_choices = (('name', _("Name"), True),
                      ('source_type', _("Source Type ="), True),
                      ('zone', _("Zone ="), True),
                      ('status', _("Status ="), True))

class TreatAction(tables.BatchAction):
    name = "treat"
    
    @staticmethod
    def action_present(count):
        return _("Processes")

    @staticmethod
    def action_past(count):
        return _("Processes")
        
    def allowed(self, request, datum):
        return datum.status_code == 'untreated'
    
    def action(self, request, obj_id):
        try:
            treatedalarm_model = treatedalarm(event_id=obj_id)
            treatedalarm_model.save()
            operate_log(request.user.username,
                            request.user.roles,
                            "alarm-event \""+obj_id+"\" treat success")
        except Exception as e:
            operate_log(request.user.username,
                            request.user.roles,
                            "alarm-event \""+obj_id+"\" treat error")
            exceptions.handle(request,
                              _('Unable to enable the policy.'))

    
class AlarmmsgTable(tables.DataTable):
    order_number = tables.Column("order_number",verbose_name=_("Order Number"))
    source_type = tables.Column("source_type",verbose_name=_("Source Type"))
    name = tables.Column("name",verbose_name=_("Name"))
    zone = tables.Column("zone",verbose_name=_("Zone"))
    alarm_content = tables.Column("alarm_content",verbose_name=_("Alarm Content"))
#     timestamp = tables.Column("timestamp",verbose_name=_("Time"))
    status = tables.Column("status",verbose_name=_("Status"))
    
    class Meta:
        name = "alarmmsg"
        verbose_name = _("Alarmmsg")
        table_actions = (AlarmmsgFilterAction,)
        row_actions = (TreatAction,)