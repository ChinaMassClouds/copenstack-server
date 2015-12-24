from horizon import tables
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext_lazy
from horizon.templatetags import sizeformat
from django import template
from django.utils.translation import pgettext_lazy
from django.core.urlresolvers import reverse_lazy
from openstack_dashboard.openstack.common.log import operate_log
from horizon import exceptions
from openstack_dashboard.models import applydisk
import datetime

class RatifyAction(tables.BatchAction):
    name = "ratify"
    success_url = reverse_lazy("horizon:admin:checkdisk:index")
    
    @staticmethod
    def action_present(count):
        return _("Approved")

    @staticmethod
    def action_past(count):
        return _("Approved")

    def action(self, request, obj_id):
        apply = applydisk.objects.filter(id=obj_id)
        apply.update(status='1')
        operate_log(request.user.username,
                    request.user.roles,
                    apply[0].name+" disk check success")


class RejectAction(tables.BatchAction):
    name = "reject"
    success_url = reverse_lazy("horizon:admin:checkdisk:index")
    
    @staticmethod
    def action_present(count):
        return _("Refuse")

    @staticmethod
    def action_past(count):
        return _("Refuse")

    def action(self, request, obj_id):
        """apply revoke"""
        apply = applydisk.objects.filter(id=obj_id)
        apply.update(status='2')
        operate_log(request.user.username,
                    request.user.roles,
                    apply[0].name+" disk check reject")


class UpdateRow(tables.Row):
    ajax = True


def get_size(volume):
    return _("%sGB") % volume.size

#apply status
APPLY_DISPLAY_CHOICES = (
    ("1", pgettext_lazy("Apply state of an Disk", _("Approved"))),
    ("2", pgettext_lazy("Apply state of an Disk", _("Refuse"))),
    ("3", pgettext_lazy("Apply state of an Disk", _("Create Success"))),
    ("4", pgettext_lazy("Apply state of an Disk", _("Create Error"))),
    ("5", pgettext_lazy("Apply state of an Disk", _("User Delete"))),
)

class CheckDiskTable(tables.DataTable):
    name = tables.Column("name",
                         verbose_name=_("Name"))
    user_name = tables.Column("user_name",
                              verbose_name=_("User name"))
    project_name = tables.Column("project_name",
                                 verbose_name=_("Project name"))
    az = tables.Column("az",
                       verbose_name=_("Availability Zone"))
    size = tables.Column(get_size,
                         verbose_name=_("Size"),
                         attrs={'data-type': 'size'})
    description = tables.Column("description",
                           verbose_name=_("Description"))
    create_date = tables.Column("create_date",
                                verbose_name=_("Create Date"),
                                filters=(lambda x:datetime.datetime.strftime(x,'%Y-%m-%d %H:%M:%S'),),
                                attrs={'data-type': 'timesince'})

    class Meta:
        name = "checkdisk"
        verbose_name = _("Check Disk")
        table_actions = (RatifyAction,RejectAction)
        row_actions = (RatifyAction,RejectAction)




class HistoryTable(tables.DataTable):
    name = tables.Column("name",
                         verbose_name=_("Name"))
    user_name = tables.Column("user_name",
                              verbose_name=_("User name"))
    project_name = tables.Column("project_name",
                                 verbose_name=_("Project name"))
    az = tables.Column("az",
                       verbose_name=_("Availability Zone"))
    size = tables.Column(get_size,
                         verbose_name=_("Size"),
                         attrs={'data-type': 'size'})
    description = tables.Column("description",
                           verbose_name=_("Description"))
    status = tables.Column("status",
                           verbose_name=_("Status"),
                           display_choices=APPLY_DISPLAY_CHOICES)
    create_date = tables.Column("create_date",verbose_name=_("Create Date"),
                                filters=(lambda x:datetime.datetime.strftime(x,'%Y-%m-%d %H:%M:%S'),))

    class Meta:
        name = "history"
        verbose_name = _("Check History")
        row_class = UpdateRow
