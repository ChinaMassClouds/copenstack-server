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

import json

from django.core.urlresolvers import reverse
from django.http import HttpResponse   # noqa
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext_lazy as _
import django.views

from horizon import exceptions
from horizon import forms

from openstack_dashboard import api
from openstack_dashboard.api import ceilometer
from openstack_dashboard.openstack.common.mongodb import f_getMongodbIp
import sys,socket
import random
import getdatafromdb
import ConfigParser
import os


    
mongodbconn = getdatafromdb.MonitoInfoQuery(host_ip=f_getMongodbIp())


class IndexView(django.views.generic.TemplateView):
    template_name = "admin/monitorstatus/index.html"
    
    def get_context_data(self):
        request = self.request
        _domains = []
        try:
            _domains = api.nova.aggregate_details_list(self.request)
        except Exception:
            exceptions.handle(request,
                              _('Unable to retrieve source domains list.'))
        domains = []
        if _domains:
            domains = [{'id':i.id,'zone':i.availability_zone} for i in _domains]
        domains.sort(key=lambda i: i['zone'].lower())
        return {'domains':domains}

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
                point = {'unit': unit,
                         'name': getattr(resource, resource_name),
                         'data': []}
                for statistic in resource.get_meter(meter_name):
                    date = statistic.duration_end[:19]
                    value = float(getattr(statistic, stats_name))
                    point['data'].append({'x': date, 'y': value})
                series.append(point)
        return series
    
    param['meter_name'] = param.get('meter').replace(".", "_")
    resources, unit = query_data(param.get('request'),
                                 param.get('date_from'),
                                 param.get('date_to'),
                                 param.get('date_options'),
                                 param.get('group_by'),
                                 param.get('meter'),
                                 query = param.get('query'))
    resource_name = 'id' if param.get('group_by') == "project" else 'resource_id'
    series = _series_for_meter(resources,
                                resource_name,
                                param.get('meter_name'),
                                param.get('stats_attr'),
                                unit)

    ret = {}
    ret['series'] = series
    ret['settings'] = {}
    return ret

class CpuMonitorView(django.views.generic.TemplateView):
    template_name = "admin/monitorstatus/cpumonitor.csv"

    def get(self, request, *args, **kwargs):
        select_domain = request.GET.get('select_domain', None)
        select_source = request.GET.get('select_source', None)
        select_target = request.GET.get('select_target', None)

        if not select_domain or not select_source or not select_target:
            return HttpResponse(json.dumps({}),
                                content_type='application/json')

#         if select_source == 'host':
#             meter = 'hardware.cpu.load.1min'
#             query = [{'field':'resource_id','value':getIpByHostname(select_target) }]
#         else:
#             meter = 'cpu_util'
#             query = [{'field':'resource_id','value':select_target}]
# 
#         param = {'request':request,
#                  'date_options':'1',
#                  'meter':meter,
#                  'query':query,
#                  'stats_attr':'avg'
#                  }
        if select_source == 'host':
            meter1 = 'hardware.cpu.load.1min'
        else:
            meter1 = 'cpu_util'
        data_list1,unit = mongodbconn.getSampleDatas(select_target,meter1,-1,100)

        ret1 = {'series':[{'data':data_list1,'name':'CPU','unit':unit}],'settings':{}}

        return HttpResponse(json.dumps(ret1),
            content_type='application/json')
        
class MemMonitorView(django.views.generic.TemplateView):
    template_name = "admin/monitorstatus/memmonitor.csv"
    
    def get(self, request, *args, **kwargs):
        select_domain = request.GET.get('select_domain', None)
        select_source = request.GET.get('select_source', None)
        select_target = request.GET.get('select_target', None)

        if not select_domain or not select_source or not select_target:
            return HttpResponse(json.dumps({}),
                                content_type='application/json')

#         if select_source == 'host':
#             query = [{'field':'resource_id','value':getIpByHostname(select_target)}]
#             meter = 'hardware.memory.used'
#         else:
#             query = [{'field':'resource_id','value':select_target}]
#             meter = 'memory.usage'
#             
#         param = {'request':request,
#                  'date_options':'1',
#                  'meter':meter,
#                  'query':query,
#                  'stats_attr':'avg'
#                  }
#         ret = commonMeterDef(param)

        if select_source == 'host':
            meter1 = 'hardware.memory.used'
#             select_target = getIpByHostname(select_target)
        else:
            meter1 = 'memory.usage'
        data_list1,unit = mongodbconn.getSampleDatas(select_target,meter1,-1,100)
#         data_list1 = []
        ret1 = {'series':[{'data':data_list1,'name':'Memory','unit':unit}],'settings':{}}

        return HttpResponse(json.dumps(ret1),
            content_type='application/json')
        
class DiskMonitorView(django.views.generic.TemplateView):
    template_name = "admin/monitorstatus/netmonitor.csv"
    
    def get(self, request, *args, **kwargs):
        select_domain = request.GET.get('select_domain', None)
        select_source = request.GET.get('select_source', None)
        select_target = request.GET.get('select_target', None)

        if not select_domain or not select_source or not select_target:
            return HttpResponse(json.dumps({}),
                                content_type='application/json')
            
#         if select_source == 'host':
#             meter1 = 'hardware.system_stats.io.outgoing.blocks'
#             query = [{'field':'resource_id','value':getIpByHostname(select_target)}]
#         else:
#             meter1 = 'disk.read.bytes.rate'
#             query = [{'field':'resource_id','value':select_target}]
#             
#         param1 = {'request':request,
#                  'date_options':'1',
#                  'meter':meter1,
#                  'query':query,
#                  'stats_attr':'avg'
#                  }
#         ret1 = commonMeterDef(param1)
        if select_source == 'host':
            meter1 = 'hardware.disk.read.bytes'
#             select_target = getIpByHostname(select_target)
        else:
            meter1 = 'disk.read.bytes.rate'
        data_list1,unit = mongodbconn.getSampleDatas(select_target,meter1,-1,100)
#         data_list1 = []
        ret1 = {'series':[{'data':data_list1,'name':select_target,'unit':unit}],'settings':{}}


        for r in ret1['series']:
            r['name'] = 'read'
        
#         if select_source == 'host':
#             meter2 = 'hardware.system_stats.io.incoming.blocks'
#         else:
#             meter2 = 'disk.write.bytes.rate'
#             
#         param2 = {'request':request,
#                  'date_options':'1',
#                  'meter':meter2,
#                  'query':query,
#                  'stats_attr':'avg'
#                  }
#         ret2 = commonMeterDef(param2)

        if select_source == 'host':
            meter2 = 'hardware.disk.write.bytes'
        else:
            meter2 = 'disk.write.bytes.rate'
        data_list2,unit = mongodbconn.getSampleDatas(select_target,meter2,-1,100)
#         data_list2 = []
        ret2 = {'series':[{'data':data_list2,'name':select_target,'unit':unit}],'settings':{}}
        
        for r in ret2['series']:
            r['name'] = 'write'
        
        ret = {}
        ret['series'] = ret1['series'] + ret2['series']
        ret['settings'] = {}

        return HttpResponse(json.dumps(ret),
            content_type='application/json')
        
class NetMonitorView(django.views.generic.TemplateView):
    template_name = "admin/monitorstatus/netmonitor.csv"
    
    def get(self, request, *args, **kwargs):
        select_domain = request.GET.get('select_domain', None)
        select_source = request.GET.get('select_source', None)
        select_target = request.GET.get('select_target', None)

        if not select_domain or not select_source or not select_target:
            return HttpResponse(json.dumps({}),
                                content_type='application/json')
            
        if select_source == 'host':
            meter1 = 'hardware.network.incoming.bytes'
#             select_target = getIpByHostname(select_target)
            data_list1,unit = mongodbconn.getSampleDatas(select_target,meter1,-1,100)
#             data_list1 = []
            ret1 = {'series':[{'data':data_list1,'name':select_target,'unit':unit}],'settings':{}}

            meter2 = 'hardware.network.outcoming.bytes'
            data_list2,unit = mongodbconn.getSampleDatas(select_target,meter2,-1,100)
#             data_list2 = []
            ret2 = {'series':[{'data':data_list2,'name':select_target,'unit':unit}],'settings':{}}
        else:
            meter1 = 'network.incoming.bytes.rate'
#             select_target = getIpByHostname(select_target)
            data_list1,unit = mongodbconn.getSampleDatas(select_target,meter1,-1,100)
#             data_list1 = []
            ret1 = {'series':[{'data':data_list1,'name':select_target,'unit':unit}],'settings':{}}

            meter2 = 'network.outgoing.bytes.rate'
            data_list2,unit = mongodbconn.getSampleDatas(select_target,meter2,-1,100)
#             data_list2 = []
            ret2 = {'series':[{'data':data_list2,'name':select_target,'unit':unit}],'settings':{}}
#             query = [{'field':'metadata.instance_id','value':select_target}]
#             meter1 = 'network.incoming.bytes.rate'
#             param1 = {'request':request,
#                      'date_options':'1',
#                      'meter':meter1,
#                      'query':query,
#                      'stats_attr':'avg'
#                      }
#             ret1 = commonMeterDef(param1)
#         
#             meter2 = 'network.outgoing.bytes.rate'
#             param2 = {'request':request,
#                      'date_options':'1',
#                      'meter':meter2,
#                      'query':query,
#                      'stats_attr':'avg'
#                      }
#             ret2 = commonMeterDef(param2)

        for r in ret1['series']:
            r['name'] = 'incoming'
        for r in ret2['series']:
            r['name'] = 'outgoing'
        
        ret = {}
        ret['series'] = ret1['series'] + ret2['series']
        ret['settings'] = {}

        return HttpResponse(json.dumps(ret),
            content_type='application/json')

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

