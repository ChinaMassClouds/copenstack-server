import django.views

from django.utils.translation import ugettext_lazy as _
from horizon import exceptions
from horizon import messages
from openstack_dashboard import api
from openstack_dashboard.openstack.common.requestapi import RequestApi,def_vcenter_vms,def_cserver_vms
import logging

LOG = logging.getLogger(__name__)

class IndexView(django.views.generic.TemplateView):
    template_name = "admin/logictopo/index.html"
    
    def get_context_data(self):
        _zones = self.get_zones()
        _plats = self.get_plats()
        _datacenters = self.get_datacenters()
        _clusters = self.get_clusters()
        _hosts = self.get_hosts()
        _vms = self.get_vms(_plats)
        (rootnode,zones,plats,datacenters,clusters,hosts,vms,computers) = self.modify_data(_zones,_plats,
                                                                                           _datacenters,_clusters,
                                                                                           _hosts,_vms)

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
        return {'nodes':rootnode + zones + plats + datacenters + clusters + hosts + vms + computers}
    
    def modify_data(self,_zones,_plats,_datacenters,_clusters,_hosts,_vms):
        rootnode = [{'level':0,
                      'type':'openstack',
                      'name':'OpenStack',
                      'no':0}]
        memberships = []
        zones = []
        plats = []
        datacenters = []
        clusters = []
        hosts = []
        vms = []
        computers = []
        no = 0
        for z in _zones:
            no += 1
            zone_no = no
            zones.append({'level':1,
                          'type':'zone',
                          'name':z.availability_zone,
                          'no':zone_no})
            memberships.append('0-' + str(zone_no))
            if getattr(z,'hosts',[]) and getattr(z,'availability_zone','') not in [p.get('domain_name') for p in _plats]:
                for j in z.hosts:
                    no += 1
                    computers.append({'level':2,
                                  'type':'computer',
                                  'name':j,
                                  'no':no})
                    memberships.append(str(zone_no) + '-' + str(no))
            
        for p in _plats:
            virtualplatformtype = p.get('virtualplatformtype')
            domain_name = p.get('domain_name')
            for zz in zones:
                if zz.get('name') == domain_name:
                    no += 1
                    plats.append({'level':2,
                              'type':'plat',
                              'name':virtualplatformtype,
                              'zone':domain_name,
                              'no':no})
                    memberships.append(str(zz.get('no')) + '-' + str(no))
                    break
                
        for p in _datacenters:
            no += 1
            datacenters.append({'level':3,
                      'type':'datacenter',
                      'name':p.get('name'),
                      'no':no})
            for i in plats:
                if p.get('domain') == i.get('zone'):
                    memberships.append(str(i.get('no')) + '-' + str(no))
                    break
                
        for p in _clusters:
            no += 1
            clusters.append({'level':4,
                      'type':'cluster',
                      'name':p.get('name'),
                      'no':no})
            for i in datacenters:
                if p.get('datacenter') == i.get('name'):
                    memberships.append(str(i.get('no')) + '-' + str(no))
                    break
            
        for h in _hosts:
            datacenter_name = h.get('datacenter')
            datacenter_no = None
            for c in datacenters:
                if datacenter_name == c.get('name'):
                    datacenter_no = c.get('no')
            if not datacenter_no:
                no += 1
                datacenter_no = no
                datacenters.append({'level':3,
                              'type':'datacenter',
                              'name':datacenter_name,
                              'no':no})
                for pp in plats:
                    if pp.get('zone') == h.get('domain'):
                        memberships.append(str(pp.get('no')) + '-' + str(no))
                
            cluster_name = h.get('cluster')
            cluster_no = None
            for c2 in clusters:
                if cluster_name == c2.get('name'):
                    cluster_no = c2.get('no')
            if not cluster_no:
                no += 1
                cluster_no = no
                clusters.append({'level':4,
                              'type':'cluster',
                              'name':cluster_name,
                              'no':cluster_no})
                memberships.append(str(datacenter_no) + '-' + str(cluster_no))

            no += 1
            host_no = no
            hosts.append({'level':5,
                          'type':'host',
                          'name':h.get('name'),
                          'no':host_no})
            memberships.append(str(cluster_no) + '-' + str(host_no))

        for v in _vms:
            appended = False
            for h in hosts:
                if h.get('name') == getattr(v,'OS-EXT-SRV-ATTR:host'):
                    no += 1
                    vms.append({'level':6,
                                  'type':'vm',
                                  'name':v.name,
                                  'host':getattr(v,'OS-EXT-SRV-ATTR:host'),
                                  'no':no})
                    appended = True
                    memberships.append(str(h.get('no')) + '-' + str(no))
                    break
            if not appended:
                for h in computers:
                    if h.get('name') == getattr(v,'OS-EXT-SRV-ATTR:host'):
                        no += 1
                        vms.append({'level':3,
                                      'type':'vm',
                                      'name':v.name,
                                      'host':getattr(v,'OS-EXT-SRV-ATTR:host'),
                                      'no':no})
                        appended = True
                        memberships.append(str(h.get('no')) + '-' + str(no))
                        break
            if not appended and getattr(v,'OS-EXT-SRV-ATTR:host',''):
                no += 1
                computer_no = no
                computers.append({'level':2,
                                  'type':'computer',
                                  'name':getattr(v,'OS-EXT-SRV-ATTR:host'),
                                  'no':computer_no})
                no += 1
                vms.append({'level':3,
                          'type':'vm',
                          'name':v.name,
                          'host':getattr(v,'OS-EXT-SRV-ATTR:host'),
                          'no':no})
                memberships.append(str(computer_no) + '-' + str(no))

        for i in rootnode + zones + plats + datacenters + clusters + hosts + vms + computers:
            i['child'] = []
            for m in memberships:
                arr = m.split('-')
                if str(i.get('no')) == arr[0]:
                    i['child'].append(int(arr[1]))
        zones.sort(cmp = lambda x,y:len(y.get('child')) - len(x.get('child')))
        plats.sort(cmp = lambda x,y:len(y.get('child')) - len(x.get('child')))
        datacenters.sort(cmp = lambda x,y:len(y.get('child')) - len(x.get('child')))
        clusters.sort(cmp = lambda x,y:len(y.get('child')) - len(x.get('child')))
        hosts.sort(cmp = lambda x,y:len(y.get('child')) - len(x.get('child')))
        vms.sort(key = lambda x : x.get('host'))

        return (rootnode,zones,plats,datacenters,clusters,hosts,vms,computers)
    
    def get_zones(self):
        request = self.request
        aggregates = []
        try:
            aggregates = api.nova.aggregate_details_list(self.request)
        except Exception:
            exceptions.handle(request,
                              _('Unable to retrieve source domains list.'))
        aggregates.sort(key=lambda aggregate: aggregate.name.lower())
        return aggregates
    
    def get_hosts(self):
        request = self.request
        datacenters = []
        clusters = []
        try:
            request_api = RequestApi()
            hosts = request_api.getRequestInfo('api/heterogeneous/platforms/hosts')
            if hosts:
                hosts.sort(key=lambda aggregate: aggregate['name'].lower())
                return hosts
        except Exception:
            exceptions.handle(request,
                              _('Unable to retrieve hosts list.'))
        return []
    
    def get_plats(self):
        plats = []
        err_msg = 'Unable to retrieve heterogeneous platforms list.'
        try:
            request_api = RequestApi()
            plats = request_api.getRequestInfo('api/heterogeneous/platforms')
    
            if plats == None or type(plats) != type([]):
                messages.error(self.request,_(err_msg))
                return []
            
            plats.sort(key=lambda aggregate: aggregate['name'].lower())
            return plats
        except Exception:
            exceptions.handle(self.request,_(err_msg))
        return []
    
    def get_datacenters(self):
        datacenters = []
        err_msg = 'Unable to retrieve datacenters list.'
        try:
            request_api = RequestApi()
            datacenters = request_api.getRequestInfo('api/heterogeneous/platforms/datacenters')
    
            if datacenters == None or type(datacenters) != type([]):
                messages.error(self.request,_(err_msg))
                return []
            
            datacenters.sort(key=lambda aggregate: aggregate['name'].lower())
            return datacenters
        except Exception:
            exceptions.handle(self.request,_(err_msg))
        return []

    def get_clusters(self):
        clusters = []
        err_msg = 'Unable to retrieve clusters list.'
        try:
            request_api = RequestApi()
            clusters = request_api.getRequestInfo('api/heterogeneous/platforms/clusters')
    
            if clusters == None or type(clusters) != type([]):
                messages.error(self.request,_(err_msg))
                return []
            
            clusters.sort(key=lambda aggregate: aggregate['name'].lower())
            return clusters
        except Exception:
            exceptions.handle(self.request,_(err_msg))
        return []

    def get_vms(self,_plats):
        plat_vcenter_vms = self.plat_vcenter_vms(_plats)
        plat_cserver_vms = self.plat_cserver_vms(_plats)
        try:
            instances, self._more = api.nova.server_list(
                self.request,
                all_tenants=True)

            if plat_vcenter_vms:
                for i in instances:
                    for v in plat_vcenter_vms:
                        if getattr(i,'id','') == v.get('id'):
                            setattr(i,'OS-EXT-SRV-ATTR:host',v.get('host'))
                            break
            if plat_cserver_vms:
                for i in instances:
                    for v in plat_cserver_vms:
                        if getattr(i,'id','') == v.get('openstack_uuid'):
                            setattr(i,'OS-EXT-SRV-ATTR:host',v.get('hostname'))
                            break
            return instances
        except Exception:
            exceptions.handle(self.request,
                              _('Unable to retrieve instance list.'))
            return []
        
    def plat_vcenter_vms(self,_plats):
        res = []
        for p in _plats:
            if p.get('virtualplatformtype') == 'vcenter':
                res += def_vcenter_vms(p.get('name'))
        return res
    
    def plat_cserver_vms(self,_plats):
        res = []
        for p in _plats:
            if p.get('virtualplatformtype') == 'cserver':
                res += def_cserver_vms(p.get('name'))
        return res