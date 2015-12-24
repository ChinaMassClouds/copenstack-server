from horizon import tables
from django.utils.translation import ugettext_lazy as _

class DataCenterTable(tables.DataTable):
    name = tables.Column("name",verbose_name=_("Name"))
    mcenter = tables.Column("mcenter",verbose_name=_("Control Center"))
    cpu = tables.Column("cpu",verbose_name=_("CPU"))
    memory = tables.Column("memory",verbose_name=_("RAM"))
    capacity = tables.Column("capacity",verbose_name=_("Assigned Storage"))
    used = tables.Column("used",verbose_name=_("Used Storage"))
    total_storage = tables.Column("total_storage",verbose_name=_("Total Storage"))
    domain = tables.Column("domain",verbose_name=_("Belonged Source Domain"))
    
    class Meta:
        name = "data_center"
        verbose_name = _("Data Center")
