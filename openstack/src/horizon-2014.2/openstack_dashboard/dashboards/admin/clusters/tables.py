from horizon import tables
from django.utils.translation import ugettext_lazy as _

class ClustersFilterAction(tables.FilterAction):
    def filter(self, table, clusters, filter_string):
        q = filter_string.lower()

        def comp(cluster):
            return q in cluster.name.lower()

        return filter(comp, clusters)



class ClustersTable(tables.DataTable):
    name = tables.Column("name",verbose_name=_("Name"))
    datacenter = tables.Column("datacenter",verbose_name=_("Data Center"))
    virtualplatformtype = tables.Column("virtualplatformtype",verbose_name=_("Virtual Type"))
    domain = tables.Column("domain",verbose_name=_("Belonged Source Domain"))
    cpu = tables.Column("cpu",verbose_name=_("CPU"))
    memory = tables.Column("memory",verbose_name=_("RAM"))
    total = tables.Column("total",verbose_name=_("Assigned Storage"))
    used = tables.Column("used",verbose_name=_("Used Storage"))
    total_storage = tables.Column("total_storage",verbose_name=_("Total Storage"))
    
    class Meta:
        name = "clusters"
        verbose_name = _("Clusters")
        table_actions = (ClustersFilterAction,)
        
    def get_columns(self):
        self.columns['multi_select'].attrs = {'class':'hide'}
        return self.columns.values()