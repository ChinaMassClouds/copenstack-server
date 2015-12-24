from horizon import tables
from django.utils.translation import ugettext_lazy as _

class HostFilterAction(tables.FilterAction):
    def filter(self, table, availability_zones, filter_string):
        q = filter_string.lower()

        def comp(availabilityZone):
            return q in availabilityZone.name.lower()

        return filter(comp, availability_zones)
    
class HostTable(tables.DataTable):
    status_choices = (('green',True),
                      ('yellow',True),
                      ('gray',True),
                      ('red',True))
    name = tables.Column("name",verbose_name=_("Name"))
    datacenter = tables.Column("datacenter",verbose_name=_("Data Center"))
    domain = tables.Column("domain",verbose_name=_("Belonged Source Domain"))
    cluster = tables.Column("cluster",verbose_name=_("Clusters"))
    status = tables.Column("status",verbose_name=_("Status"),status=True,status_choices=status_choices)
    cpu = tables.Column("cpu",verbose_name=_("CPU cores"))
    memory = tables.Column("memory",verbose_name=_("RAM"))
    cpu_utilization = tables.Column("cpu_utilization",verbose_name=_("CPU utilization"))
    network_utilization = tables.Column("network_utilization",verbose_name=_("Network utilization"))
    
    class Meta:
        name = "host"
        verbose_name = _("Host")
        table_actions = (HostFilterAction,)
        
    def get_columns(self):
        self.columns['multi_select'].attrs = {'class':'hide'}
        return self.columns.values()