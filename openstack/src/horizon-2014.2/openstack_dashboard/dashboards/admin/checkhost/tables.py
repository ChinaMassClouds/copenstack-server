from horizon import tables
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext_lazy
from openstack_dashboard.models import apply
from horizon.templatetags import sizeformat
from django import template
from django.utils.translation import pgettext_lazy
from django.core.urlresolvers import reverse_lazy
from openstack_dashboard.openstack.common.log import operate_log
from horizon import exceptions
import datetime

class RatifyAction(tables.BatchAction):
    name = "ratify"
    success_url = reverse_lazy("horizon:admin:checkhost:index")
    
    @staticmethod
    def action_present(count):
        return _("Approved")

    @staticmethod
    def action_past(count):
        return _("Approved")

    def action(self, request, obj_id):
        apply_instances = apply.objects.filter(id=obj_id)
        apply_instances.update(status='1')
        operate_log(request.user.username,
                    request.user.roles,
                    apply_instances[0].name+" instances check success")


class RejectAction(tables.BatchAction):
    name = "reject"
    success_url = reverse_lazy("horizon:admin:checkhost:index")
    
    @staticmethod
    def action_present(count):
        return _("Refuse")

    @staticmethod
    def action_past(count):
        return _("Refuse")

    def action(self, request, obj_id):
        """
        apply revoke
        """
        apply_instances = apply.objects.filter(id=obj_id)
        apply_instances.update(status='2')
        operate_log(request.user.username,
                    request.user.roles,
                    apply_instances[0].name+" instances check reject")


class UpdateRow(tables.Row):
    ajax = True


def get_size(instance):
    if hasattr(instance, "full_flavor"):
        template_name = 'project/applyhost/_instance_flavor.html'
        size_ram = sizeformat.mb_float_format(instance.full_flavor.ram)
        if instance.full_flavor.disk > 0:
            size_disk = sizeformat.diskgbformat(instance.full_flavor.disk)
        else:
            size_disk = _("%s GB") % "0"
        context = {
            "name": instance.full_flavor.name,
            "id": instance.id,
            "size_disk": size_disk,
            "size_ram": size_ram,
            "vcpus": instance.full_flavor.vcpus
        }
        return template.loader.render_to_string(template_name, context)
    return _("Not available")


class CheckHostTable(tables.DataTable):
    name = tables.Column("name",
                         verbose_name=_("Name"))
    user_name = tables.Column("user_name",
                              verbose_name=_("User name"))
    project_name = tables.Column("project_name",
                                 verbose_name=_("Project name"))
    az = tables.Column("avail_zone",
                       verbose_name=_("Availability Zone"))
    size = tables.Column(get_size,
                         verbose_name=_("Size"),
                         attrs={'data-type': 'size'})
    image_name = tables.Column("image_name",
                               verbose_name=_("Image Name"))
    count = tables.Column("count",
                          verbose_name=_("Count"))
    reason = tables.Column("info",
                           verbose_name=_("Reason"))
    create_date = tables.Column("create_date",
                                filters=(lambda x:datetime.datetime.strftime(x,'%Y-%m-%d %H:%M:%S'),),
                                verbose_name=_("Create Date"))

    class Meta:
        name = "checkhost"
        verbose_name = _("Check Host")
        table_actions = (RatifyAction,RejectAction)
        row_actions = (RatifyAction,RejectAction)


#apply status
APPLY_DISPLAY_CHOICES = (
    ("1", pgettext_lazy("Apply state of an Instance", _("Approved"))),
    ("2", pgettext_lazy("Apply state of an Instance", _("Refuse"))),
    ("3", pgettext_lazy("Apply state of an Instance", _("Create Success"))),
    ("4", pgettext_lazy("Apply state of an Instance", _("Create Error"))),
    ("5", pgettext_lazy("Apply state of an Instance", _("User Delete"))),
)


class HistoryTable(tables.DataTable):
    name = tables.Column("name",
                         verbose_name=_("Name"))
    user_name = tables.Column("user_name",
                              verbose_name=_("User name"))
    project_name = tables.Column("project_name",
                                 verbose_name=_("Project name"))
    az = tables.Column("avail_zone",
                       verbose_name=_("Availability Zone"))
    size = tables.Column(get_size,
                         verbose_name=_("Size"),
                         attrs={'data-type': 'size'})
    image_name = tables.Column("image_name",
                               verbose_name=_("Image Name"))
    count = tables.Column("count",
                          verbose_name=_("Count"))
    reason = tables.Column("info",
                           verbose_name=_("Reason"))
    status = tables.Column("status",
                           verbose_name=_("Status"),
                           display_choices=APPLY_DISPLAY_CHOICES)
    create_date = tables.Column("create_date",verbose_name=_("Create Date"),
                                filters=(lambda x:datetime.datetime.strftime(x,'%Y-%m-%d %H:%M:%S'),))

    class Meta:
        name = "history"
        verbose_name = _("Check History")
        row_class = UpdateRow
