# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from datetime import datetime  # noqa
from datetime import timedelta  # noqa
from horizon import tabs
import json

from django.http import HttpResponse   # noqa
from django.utils.translation import ugettext_lazy as _
import django.views

from horizon import exceptions
from horizon import forms

from openstack_dashboard import api
from openstack_dashboard.api import ceilometer
import sys,socket
from openstack_dashboard.dashboards.admin.monitoroverview import tabs as monitoroverview_tabs
import Top
from openstack_dashboard.openstack.common.mongodb import f_getMongodbIp
import logging

LOG = logging.getLogger(__name__)

cost_top = Top.Top(host_ip=f_getMongodbIp())
g_instance_id_name = {}

def get_instance_id_name(request):
    global g_instance_id_name
    try:
        instances, _more = api.nova.server_list(
            request,
            all_tenants=True)
        if instances:
            for i in instances:
                g_instance_id_name[i.id] = i.name
    except Exception:
        exceptions.handle(request,
                          _('Unable to retrieve instance list.'))

class IndexView(tabs.TabbedTableView):
    tab_group_class = monitoroverview_tabs.CeilometerOverviewTabs
    template_name = 'admin/monitoroverview/index.html'

def commonMeterDef(param):
    def _series_for_meter(aggregates,
                          resource_name,
                          meter_name,
                          stats_name,
                          unit):
        """Construct datapoint series for a meter from resource aggregates."""
        series = []

        for resource in aggregates:
            if resource.get_meter(meter_name):
                for statistic in resource.get_meter(meter_name):
                    date = statistic.duration_end[:19]
                    value = float(getattr(statistic, stats_name))
                    name = getattr(resource, 'metadata').get('display_name') or getattr(resource, 'resource_id')
                    series.append({'x': date, 'y': value,'name':name})
        return series
    
    resource_name = 'id' if param.get('group_by') == "project" else 'resource_id'
    
    param['meter_name'] = param.get('meter').replace(".", "_")
    resources, unit = query_data(param.get('request'),
                                 param.get('date_from'),
                                 param.get('date_to'),
                                 param.get('date_options'),
                                 param.get('group_by'),
                                 param.get('meter'),
                                 query = param.get('query'))
    series = _series_for_meter(resources,
                                resource_name,
                                param.get('meter_name'),
                                param.get('stats_attr'),
                                unit)
    
    if param.get('meter2'):
        param['meter_name2'] = param.get('meter2').replace(".", "_")
        resources2, unit2 = query_data(param.get('request'),
                                 param.get('date_from'),
                                 param.get('date_to'),
                                 param.get('date_options'),
                                 param.get('group_by'),
                                 param.get('meter2'),
                                 query = param.get('query'))
        series2 = _series_for_meter(resources2,
                                resource_name,
                                param.get('meter_name2'),
                                param.get('stats_attr'),
                                unit2)
        for i in series:
            for j in series2:
                if i['x'] == j['x'] and i['name'] == j['name']:
                    i['y'] += j['y']
                    
    elif param.get('meter3'):
        param['meter_name3'] = param.get('meter3').replace(".", "_")
        resources3, unit3 = query_data(param.get('request'),
                                 param.get('date_from'),
                                 param.get('date_to'),
                                 param.get('date_options'),
                                 param.get('group_by'),
                                 param.get('meter3'),
                                 query = param.get('query'))
        series3 = _series_for_meter(resources3,
                                resource_name,
                                param.get('meter_name3'),
                                param.get('stats_attr'),
                                unit3)

        if series3 and series3[0]:
            total = series3[0]['y']
            if total > 0:
                for i in series:
                    i['y'] = i['y'] / total * 100
            
    x_labels = []
    y_series = []
    if series:
        series.sort(cmp = lambda obj1,obj2: cmp(obj2.get('x'),obj1.get('x')))
        the_time = series[0].get('x')
        picked_series = [i for i in series if i.get('x') == the_time]
        picked_series.sort(cmp = lambda obj1,obj2: cmp(obj2.get('y'),obj1.get('y')))
        picked_series = picked_series[0:5]
        for i in range(len(picked_series)):
            x_labels.append(picked_series[i].get('name'))
            y_series.append(picked_series[i].get('y'))

    return {'x_labels':x_labels,'y_series':y_series}

def modify_result(src_data,request,need_get_name):
    try:
        x_labels = []
        y_series = []
        for d in src_data:
            if d.get('counter_volume') and d.get('counter_volume') != 0:
                if need_get_name:
                    i_name = g_instance_id_name.get(d.get('resource_id'))
                    if not i_name:
                        get_instance_id_name(request)
                        i_name = g_instance_id_name.get(d.get('resource_id'))
                    if not i_name:
                        i_name = d.get('resource_id')
                    x_labels.append(i_name)
                else:
                    x_labels.append(d.get('resource_id'))
                y_series.append(d.get('counter_volume'))
        res_data = {'x_labels':x_labels,'y_series':y_series}
    except Exception as e:
        res_data = {'x_labels':[],'y_series':[]}
    return  res_data

def cpu_monitor(request, target_type):
    if not target_type:
        return HttpResponse(json.dumps({}),
                            content_type='application/json')

    if target_type == 'host':
        meter = 'hardware.cpu.load.1min'
    else:
        meter = 'cpu_util'

    cost_top.setCollection("ceilometer","meter")
    collection = cost_top.top(meter)

    res = json.dumps( modify_result(collection,request,target_type == 'vm'))
    
    return HttpResponse(res,content_type='application/json')

def mem_monitor(request, target_type):
    if not target_type:
        return HttpResponse(json.dumps({}),
                            content_type='application/json')

    if target_type == 'host':
        meter = 'hardware.memory.used'
    else:
        meter = 'memory.usage'

    cost_top.setCollection("ceilometer","meter")
    collection = cost_top.top(meter)
    res = json.dumps( modify_result(collection,request,target_type == 'vm'))

    return HttpResponse(res,content_type='application/json')

def disk_monitor(request, target_type):
    if not target_type:
        return HttpResponse(json.dumps({}),
                            content_type='application/json')

    if target_type == 'host':
        meter = 'hardware.disk.size.used'
    else:
        meter = 'disk.usage'

    cost_top.setCollection("ceilometer","meter")
    collection = cost_top.top(meter)
    res = json.dumps( modify_result(collection,request,target_type == 'vm'))
    
    return HttpResponse(res,content_type='application/json')
    
def net_monitor(request, target_type):
    if not target_type:
        return HttpResponse(json.dumps({}),
                            content_type='application/json')

    if target_type == 'host':
        meter = 'hardware.network.bytes'
    else:
        meter = 'network.bytes'

    cost_top.setCollection("ceilometer","meter")
    collection = cost_top.top(meter)
    res = json.dumps( modify_result(collection,request,target_type == 'vm'))
    
    return HttpResponse(res,content_type='application/json')

def _calc_period(date_from, date_to):
    if date_from and date_to:
        if date_to < date_from:
            # TODO(lsmola) propagate the Value error through Horizon
            # handler to the client with verbose message.
            raise ValueError("Date to must be bigger than date "
                             "from.")
            # get the time delta in seconds
        delta = date_to - date_from
        if delta.days <= 0:
            # it's one day
            delta_in_seconds = 3600 * 24
        else:
            delta_in_seconds = delta.days * 24 * 3600 + delta.seconds
            # Lets always show 400 samples in the chart. Know that it is
        # maximum amount of samples and it can be lower.
        number_of_samples = 400
        period = delta_in_seconds / number_of_samples
    else:
        # If some date is missing, just set static window to one day.
        period = 3600 * 24
    return period


def _calc_date_args(date_from, date_to, date_options):
    # TODO(lsmola) all timestamps should probably work with
    # current timezone. And also show the current timezone in chart.
    if (date_options == "other"):
        try:
            if date_from:
                date_from = datetime.strptime(date_from,
                                              "%Y-%m-%d")
            else:
                # TODO(lsmola) there should be probably the date
                # of the first sample as default, so it correctly
                # counts the time window. Though I need ordering
                # and limit of samples to obtain that.
                pass
            if date_to:
                date_to = datetime.strptime(date_to,
                                            "%Y-%m-%d")
                # It return beginning of the day, I want the and of
                # the day, so i will add one day without a second.
                date_to = (date_to + timedelta(days=1) -
                           timedelta(seconds=1))
            else:
                date_to = datetime.now()
        except Exception:
            raise ValueError("The dates are not "
                             "recognized.")
    else:
        try:
            date_from = datetime.now() - timedelta(days=int(date_options))
            date_to = datetime.now()
        except Exception:
            raise ValueError("The time delta must be an "
                             "integer representing days.")
    return date_from, date_to


def query_data(request,
               date_from,
               date_to,
               date_options,
               group_by,
               meter,
               period=None,
               additional_query=None,
               query=None):
    date_from, date_to = _calc_date_args(date_from,
                                         date_to,
                                         date_options)
    if not period:
        period = _calc_period(date_from, date_to)
    if additional_query is None:
        additional_query = []
    if date_from:
        additional_query += [{'field': 'timestamp',
                              'op': 'ge',
                              'value': date_from}]
    if date_to:
        additional_query += [{'field': 'timestamp',
                              'op': 'le',
                              'value': date_to}]

    # TODO(lsmola) replace this by logic implemented in I1 in bugs
    # 1226479 and 1226482, this is just a quick fix for RC1
    try:
        meter_list = [m for m in ceilometer.meter_list(request)
                      if m.name == meter]
        unit = meter_list[0].unit
    except Exception:
        unit = ""
    if group_by == "project":
        try:
            tenants, more = api.keystone.tenant_list(
                request,
                domain=None,
                paginate=False)
        except Exception:
            tenants = []
            exceptions.handle(request,
                              _('Unable to retrieve project list.'))
        queries = {}
        for tenant in tenants:
            tenant_query = [{
                            "field": "project_id",
                            "op": "eq",
                            "value": tenant.id}]

            queries[tenant.name] = tenant_query

        ceilometer_usage = ceilometer.CeilometerUsage(request)
        resources = ceilometer_usage.resource_aggregates_with_statistics(
            queries, [meter], period=period, stats_attr=None,
            additional_query=additional_query)

    else:
        query = query or []
        
        def filter_by_meter_name(resource):
            """Function for filtering of the list of resources.

            Will pick the right resources according to currently selected
            meter.
            """
            for link in resource.links:
                if link['rel'] == meter:
                    # If resource has the currently chosen meter.
                    return True
            return False

        ceilometer_usage = ceilometer.CeilometerUsage(request)
        try:
            resources = ceilometer_usage.resources_with_statistics(
                query, [meter], period=period, stats_attr=None,
                additional_query=additional_query,
                filter_func=filter_by_meter_name)
        except Exception:
            resources = []
            exceptions.handle(request,
                              _('Unable to retrieve statistics.'))
    return resources, unit


def load_report_data(request):
    meters = ceilometer.Meters(request)
    services = {
        _('Nova'): meters.list_nova(),
        _('Neutron'): meters.list_neutron(),
        _('Glance'): meters.list_glance(),
        _('Cinder'): meters.list_cinder(),
        _('Swift_meters'): meters.list_swift(),
        _('Kwapi'): meters.list_kwapi(),
    }
    project_rows = {}
    date_options = request.GET.get('date_options', 7)
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    for meter in meters._cached_meters.values():
        service = None
        for name, m_list in services.items():
            if meter in m_list:
                service = name
                break
        # show detailed samples
        # samples = ceilometer.sample_list(request, meter.name)
        res, unit = query_data(request,
                               date_from,
                               date_to,
                               date_options,
                               "project",
                               meter.name,
                               3600 * 24)
        for re in res:
            values = re.get_meter(meter.name.replace(".", "_"))
            if values:
                for value in values:
                    row = {"name": 'none',
                           "project": re.id,
                           "meter": meter.name,
                           "description": meter.description,
                           "service": service,
                           "time": value._apiresource.period_end,
                           "value": value._apiresource.avg}
                    if re.id not in project_rows:
                        project_rows[re.id] = [row]
                    else:
                        project_rows[re.id].append(row)
    return project_rows

