from horizon import tables
from openstack_dashboard.dashboards.admin.checkdisk import tables as host_tables
from horizon import exceptions
from django.utils.translation import ugettext_lazy as _
from openstack_dashboard.models import applydisk
from openstack_dashboard import api
from django.utils.datastructures import SortedDict


class IndexView(tables.MultiTableView):
    template_name = 'admin/checkdisk/index.html'
    table_classes = (host_tables.CheckDiskTable,
                     host_tables.HistoryTable)

    def get_checkdisk_data(self):
        """
        check disk show
        """
        instances = applydisk.objects.filter(status='0')
        return instances

    def get_history_data(self):
        instances = applydisk.objects.exclude(status='0')
        return instances
