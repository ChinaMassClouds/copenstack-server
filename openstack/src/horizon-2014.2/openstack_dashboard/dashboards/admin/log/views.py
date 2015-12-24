from horizon import tables
from openstack_dashboard.dashboards.admin.log import tables as log_tables
from openstack_dashboard.models import log
from horizon.utils import functions as utils
from django.conf import settings
import itertools
from horizon import exceptions
from django.utils.translation import ugettext_lazy as _


def log_list_detailed(request, marker=None,prev_marker=None,sort_dir='desc',
                      sort_key='created_at', filters=None, paginate=False):
    limit = getattr(settings, 'API_RESULT_LIMIT', 1000)
    page_size = utils.get_page_size(request)

    if paginate:
        request_size = page_size + 1
    else:
        request_size = limit

    kwargs = {'filters': filters or {}}
    marker_index = -1
    prev_marker_index = -1
    log_all = log.objects.all().order_by('-create_date')

    ids = [i.id for i in log_all]

    log_count = log_all.count()

    if marker :
        kwargs['marker'] = marker
        marker_index = ids.index(int(marker))
    elif prev_marker:
        kwargs['prev_marker'] = prev_marker
        prev_marker_index = ids.index(int(prev_marker))
    kwargs['sort_dir'] = sort_dir
    kwargs['sort_key'] = sort_key

    has_prev_data = True
    has_more_data = True
    if marker:
        log_iter = log_all[marker_index + 1 : marker_index + request_size]
        if marker_index + request_size >= log_count:
            has_more_data = False
    elif prev_marker:
        if prev_marker_index - request_size + 1 <= 0:
            has_prev_data = False
            log_iter = log_all[0 : prev_marker_index + 1]
        else:
            log_iter = log_all[prev_marker_index - request_size + 1 : prev_marker_index + 1]
    else:
        log_iter = log_all[0 : request_size]
        has_prev_data = False
        if log_count <= page_size:
            has_more_data = False

    if paginate:
        logs = list(itertools.islice(log_iter, request_size))
        # first and middle page condition
        if len(logs) > page_size:
            logs.pop(-1)
            has_more_data = True
            # middle page condition
            if marker is not None:
                has_prev_data = True
        # first page condition when reached via prev back
        elif sort_dir == 'asc' and marker is not None:
            has_more_data = True
        # last page condition
        elif marker is not None:
            has_prev_data = True
    else:
        logs = list(log_iter)

    return (logs, has_more_data, has_prev_data)


class IndexView(tables.DataTableView):
    template_name = 'admin/log/index.html'
    table_class = log_tables.LogTable

    def has_prev_data(self, table):
        return self._prev
 
    def has_more_data(self, table):
        return self._more
 
    def get_data(self):
        marker = self.request.GET.get(log_tables.LogTable._meta.pagination_param, None) 
        prev_marker = self.request.GET.get(log_tables.LogTable._meta.prev_pagination_param, None) 
 
        try:
            (logs, self._more, self._prev) = log_list_detailed(self.request, marker=marker,
                                                                 prev_marker=prev_marker,paginate=True)
        except Exception:
            logs = []
            exceptions.handle(self.request, _("Unable to retrieve logs."))
         
        return logs