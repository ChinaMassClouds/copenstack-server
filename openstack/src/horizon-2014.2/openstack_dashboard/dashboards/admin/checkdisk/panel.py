from django.utils.translation import ugettext_lazy as _
import horizon
from openstack_dashboard.dashboards.admin import dashboard
from openstack_dashboard.openstack.common.log import policy_is


class CheckDisk(horizon.Panel):
    name = _("Volume")
    slug = 'checkdisk'
    img = '/static/dashboard/img/nav/checkdisk1.png'

    def nav(self, context):
        username = context['request'].user.username
        return policy_is(username, 'appradmin')


dashboard.Admin.register(CheckDisk)
