from horizon import tables
from openstack_dashboard.dashboards.admin.clusters \
    import tables as clusters_tables
from horizon import exceptions
from openstack_dashboard.openstack.common.requestapi import RequestApi
from openstack_dashboard.openstack.common.dictutils import DictList2ObjectList
from django.utils.translation import ugettext_lazy as _
from horizon import messages

class IndexView(tables.DataTableView):
    template_name = 'admin/clusters/index.html'
    table_class = clusters_tables.ClustersTable
    
    def get_data(self):
        request = self.request
        plats = []
        try:
            request_api = RequestApi()
            plats = request_api.getRequestInfo('api/heterogeneous/platforms/clusters')
            if plats and type([]) == type(plats):
                plats.sort(key=lambda aggregate: aggregate['name'].lower())
                res = DictList2ObjectList(plats)
                return res
            elif plats and type(plats) == type({}) and plats.get('action') == 'failed':
                messages.error(request,
                              _('Unable to retrieve clusters list.'))
        except Exception:
            exceptions.handle(request,
                              _('Unable to retrieve clusters list.'))
        return []