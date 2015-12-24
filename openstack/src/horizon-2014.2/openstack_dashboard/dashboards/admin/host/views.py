from horizon import tables
from openstack_dashboard.dashboards.admin.host import tables as host_tables
from openstack_dashboard.openstack.common.requestapi import RequestApi
from openstack_dashboard.openstack.common.dictutils import DictList2ObjectList
from horizon import exceptions
from django.utils.translation import ugettext_lazy as _
from horizon import messages

class IndexView(tables.DataTableView):
    template_name = 'admin/host/index.html'
    table_class = host_tables.HostTable
    
    def get_data(self):
        request = self.request
        plats = []
        try:
            request_api = RequestApi()
            plats = request_api.getRequestInfo('api/heterogeneous/platforms/hosts')
            if plats and type(plats) == type([]):
                plats.sort(key=lambda aggregate: aggregate['name'].lower())
                res = DictList2ObjectList(plats)
                return res
            elif plats and type(plats) == type({}) and plats.get('action') == 'failed':
                messages.error(request,
                              _('Unable to retrieve hosts list.'))
        except Exception:
            exceptions.handle(request,
                              _('Unable to retrieve hosts list.'))
        return []