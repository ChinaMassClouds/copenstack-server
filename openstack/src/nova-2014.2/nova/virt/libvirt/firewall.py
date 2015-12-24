# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# Copyright (c) 2010 Citrix Systems, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import uuid

from lxml import etree
from oslo.config import cfg

from nova.cloudpipe import pipelib
from nova.i18n import _LI
from nova.i18n import _LW
from nova.openstack.common import importutils
from nova.openstack.common import log as logging
import nova.virt.firewall as base_firewall
from nova.virt import netutils

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
CONF.import_opt('use_ipv6', 'nova.netconf')

libvirt = None


class NWFilterFirewall(base_firewall.FirewallDriver):
    """This class implements a network filtering mechanism by using
    libvirt's nwfilter.
    all instances get a filter ("nova-base") applied. This filter
    provides some basic security such as protection against MAC
    spoofing, IP spoofing, and ARP spoofing.
    """

    def __init__(self, virtapi, get_connection, **kwargs):
        super(NWFilterFirewall, self).__init__(virtapi)
        global libvirt
        if libvirt is None:
            try:
                libvirt = importutils.import_module('libvirt')
            except ImportError:
                LOG.warn(_LW("Libvirt module could not be loaded. "
                             "NWFilterFirewall will not work correctly."))
        self._libvirt_get_connection = get_connection
        self.static_filters_configured = False
        self.handle_security_groups = False

    def apply_instance_filter(self, instance, network_info):
        """No-op. Everything is done in prepare_instance_filter."""
        pass

    def _get_connection(self):
        return self._libvirt_get_connection()
    _conn = property(_get_connection)

    def nova_no_nd_reflection_filter(self):
        """This filter protects false positives on IPv6 Duplicate Address
        Detection(DAD).
        """
        uuid = self._get_filter_uuid('nova-no-nd-reflection')
        return '''<filter name='nova-no-nd-reflection' chain='ipv6'>
                  <!-- no nd reflection -->
                  <!-- drop if destination mac is v6 mcast mac addr and
                       we sent it. -->
                  <uuid>%s</uuid>
                  <rule action='drop' direction='in'>
                      <mac dstmacaddr='33:33:00:00:00:00'
                           dstmacmask='ff:ff:00:00:00:00' srcmacaddr='$MAC'/>
                  </rule>
                  </filter>''' % uuid

    def nova_dhcp_filter(self):
        """The standard allow-dhcp-server filter is an <ip> one, so it uses
           ebtables to allow traffic through. Without a corresponding rule in
           iptables, it'll get blocked anyway.
        """
        uuid = self._get_filter_uuid('nova-allow-dhcp-server')
        return '''<filter name='nova-allow-dhcp-server' chain='ipv4'>
                    <uuid>%s</uuid>
                    <rule action='accept' direction='out'
                          priority='100'>
                      <udp srcipaddr='0.0.0.0'
                           dstipaddr='255.255.255.255'
                           srcportstart='68'
                           dstportstart='67'/>
                    </rule>
                    <rule action='accept' direction='in'
                          priority='100'>
                      <udp srcipaddr='$DHCPSERVER'
                           srcportstart='67'
                           dstportstart='68'/>
                    </rule>
                  </filter>''' % uuid

    def setup_basic_filtering(self, instance, network_info):
        """Set up basic filtering (MAC, IP, and ARP spoofing protection)."""
        LOG.info(_LI('Called setup_basic_filtering in nwfilter'),
                 instance=instance)

        if self.handle_security_groups:
            # No point in setting up a filter set that we'll be overriding
            # anyway.
            return

        LOG.info(_LI('Ensuring static filters'), instance=instance)
        self._ensure_static_filters()

        nodhcp_base_filter = self.get_base_filter_list(instance, False)
        dhcp_base_filter = self.get_base_filter_list(instance, True)

        for vif in network_info:
            _base_filter = nodhcp_base_filter
            for subnet in vif['network']['subnets']:
                if subnet.get_meta('dhcp_server'):
                    _base_filter = dhcp_base_filter
                    break
            self._define_filter(self._get_instance_filter_xml(instance,
                                                              _base_filter,
                                                              vif))

    def _get_instance_filter_parameters(self, vif):
        parameters = []

        def format_parameter(parameter, value):
            return ("<parameter name='%s' value='%s'/>" % (parameter, value))

        network = vif['network']
        if not vif['network'] or not vif['network']['subnets']:
            return parameters

        v4_subnets = [s for s in network['subnets'] if s['version'] == 4]
        v6_subnets = [s for s in network['subnets'] if s['version'] == 6]

        for subnet in v4_subnets:
            for ip in subnet['ips']:
                parameters.append(format_parameter('IP', ip['address']))

            dhcp_server = subnet.get_meta('dhcp_server')
            if dhcp_server:
                parameters.append(format_parameter('DHCPSERVER', dhcp_server))
        if CONF.use_ipv6:
            for subnet in v6_subnets:
                gateway = subnet.get('gateway')
                if gateway:
                    ra_server = gateway['address'] + "/128"
                    parameters.append(format_parameter('RASERVER', ra_server))

        if CONF.allow_same_net_traffic:
            for subnet in v4_subnets:
                ipv4_cidr = subnet['cidr']
                net, mask = netutils.get_net_and_mask(ipv4_cidr)
                parameters.append(format_parameter('PROJNET', net))
                parameters.append(format_parameter('PROJMASK', mask))

            if CONF.use_ipv6:
                for subnet in v6_subnets:
                    ipv6_cidr = subnet['cidr']
                    net, prefix = netutils.get_net_and_prefixlen(ipv6_cidr)
                    parameters.append(format_parameter('PROJNET6', net))
                    parameters.append(format_parameter('PROJMASK6', prefix))

        return parameters

    def _get_instance_filter_xml(self, instance, filters, vif):
        nic_id = vif['address'].replace(':', '')
        instance_filter_name = self._instance_filter_name(instance, nic_id)
        parameters = self._get_instance_filter_parameters(vif)
        uuid = self._get_filter_uuid(instance_filter_name)
        xml = '''<filter name='%s' chain='root'>''' % instance_filter_name
        xml += '<uuid>%s</uuid>' % uuid
        for f in filters:
            xml += '''<filterref filter='%s'>''' % f
            xml += ''.join(parameters)
            xml += '</filterref>'
        xml += '</filter>'
        return xml

    def get_base_filter_list(self, instance, allow_dhcp):
        """Obtain a list of base filters to apply to an instance.
        The return value should be a list of strings, each
        specifying a filter name.  Subclasses can override this
        function to add additional filters as needed.  Additional
        filters added to the list must also be correctly defined
        within the subclass.
        """
        if pipelib.is_vpn_image(instance['image_ref']):
            base_filter = 'nova-vpn'
        elif allow_dhcp:
            base_filter = 'nova-base'
        else:
            base_filter = 'nova-nodhcp'
        return [base_filter]

    def _ensure_static_filters(self):
        """Static filters are filters that have no need to be IP aware.

        There is no configuration or tuneability of these filters, so they
        can be set up once and forgotten about.

        """

        if self.static_filters_configured:
            return

        filter_set = ['no-mac-spoofing',
                      'no-ip-spoofing',
                      'no-arp-spoofing']

        self._define_filter(self.nova_no_nd_reflection_filter())
        filter_set.append('nova-no-nd-reflection')
        self._define_filter(self._filter_container('nova-nodhcp', filter_set))
        filter_set.append('allow-dhcp-server')
        self._define_filter(self._filter_container('nova-base', filter_set))
        self._define_filter(self._filter_container('nova-vpn',
                                                   ['allow-dhcp-server']))
        self._define_filter(self.nova_dhcp_filter())

        self.static_filters_configured = True

    def _filter_container(self, name, filters):
        uuid = self._get_filter_uuid(name)
        xml = '''<filter name='%s' chain='root'>
                   <uuid>%s</uuid>
                   %s
                 </filter>''' % (name, uuid,
                 ''.join(["<filterref filter='%s'/>" % (f,) for f in filters]))
        return xml

    def _get_filter_uuid(self, name):
        try:
            flt = self._conn.nwfilterLookupByName(name)
            xml = flt.XMLDesc(0)
            doc = etree.fromstring(xml)
            u = doc.find("./uuid").text
        except Exception as e:
            LOG.debug("Cannot find UUID for filter '%s': '%s'" % (name, e))
            u = uuid.uuid4().hex

        LOG.debug("UUID for filter '%s' is '%s'" % (name, u))
        return u

    def _define_filter(self, xml):
        if callable(xml):
            xml = xml()
        self._conn.nwfilterDefineXML(xml)

    def unfilter_instance(self, instance, network_info):
        """Clear out the nwfilter rules."""
        for vif in network_info:
            nic_id = vif['address'].replace(':', '')
            instance_filter_name = self._instance_filter_name(instance, nic_id)

            try:
                _nw = self._conn.nwfilterLookupByName(instance_filter_name)
                _nw.undefine()
            except libvirt.libvirtError as e:
                errcode = e.get_error_code()
                if errcode == libvirt.VIR_ERR_OPERATION_INVALID:
                    # This happens when the instance filter is still in
                    # use (ie. when the instance has not terminated properly)
                    raise
                LOG.debug('The nwfilter(%s) is not found.',
                          instance_filter_name, instance=instance)

    @staticmethod
    def _instance_filter_name(instance, nic_id=None):
        if not nic_id:
            return 'nova-instance-%s' % (instance['name'])
        return 'nova-instance-%s-%s' % (instance['name'], nic_id)

    def instance_filter_exists(self, instance, network_info):
        """Check nova-instance-instance-xxx exists."""
        for vif in network_info:
            nic_id = vif['address'].replace(':', '')
            instance_filter_name = self._instance_filter_name(instance, nic_id)
            try:
                self._conn.nwfilterLookupByName(instance_filter_name)
            except libvirt.libvirtError:
                name = instance['name']
                LOG.debug('The nwfilter(%(instance_filter_name)s) for'
                          '%(name)s is not found.',
                          {'instance_filter_name': instance_filter_name,
                           'name': name},
                          instance=instance)
                return False
        return True


class IptablesFirewallDriver(base_firewall.IptablesFirewallDriver):
    def __init__(self, virtapi, execute=None, **kwargs):
        super(IptablesFirewallDriver, self).__init__(virtapi, **kwargs)
        self.nwfilter = NWFilterFirewall(virtapi, kwargs['get_connection'])

    def setup_basic_filtering(self, instance, network_info):
        """Set up provider rules and basic NWFilter."""
        self.nwfilter.setup_basic_filtering(instance, network_info)
        if not self.basically_filtered:
            LOG.debug('iptables firewall: Setup Basic Filtering',
                      instance=instance)
            self.refresh_provider_fw_rules()
            self.basically_filtered = True

    def apply_instance_filter(self, instance, network_info):
        """No-op. Everything is done in prepare_instance_filter."""
        pass

    def unfilter_instance(self, instance, network_info):
        # NOTE(salvatore-orlando):
        # Overriding base class method for applying nwfilter operation
        if self.instance_info.pop(instance['id'], None):
            self.remove_filters_for_instance(instance)
            self.iptables.apply()
            self.nwfilter.unfilter_instance(instance, network_info)
        else:
            LOG.info(_LI('Attempted to unfilter instance which is not '
                         'filtered'), instance=instance)

    def instance_filter_exists(self, instance, network_info):
        """Check nova-instance-instance-xxx exists."""
        return self.nwfilter.instance_filter_exists(instance, network_info)
