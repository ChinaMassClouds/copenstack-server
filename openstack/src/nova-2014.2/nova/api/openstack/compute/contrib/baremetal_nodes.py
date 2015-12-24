# Copyright (c) 2013 NTT DOCOMO, INC.
# All Rights Reserved.
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

"""The bare-metal admin extension with Ironic Proxy."""

import netaddr
from oslo.config import cfg
import webob

from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova.api.openstack import xmlutil
from nova import exception
from nova.i18n import _
from nova.openstack.common import importutils
from nova.openstack.common import log as logging
from nova.virt.baremetal import db

ironic_client = importutils.try_import('ironicclient.client')

authorize = extensions.extension_authorizer('compute', 'baremetal_nodes')

node_fields = ['id', 'cpus', 'local_gb', 'memory_mb', 'pm_address',
               'pm_user', 'service_host', 'terminal_port', 'instance_uuid']

node_ext_fields = ['uuid', 'task_state', 'updated_at', 'pxe_config_path']

interface_fields = ['id', 'address', 'datapath_id', 'port_no']

CONF = cfg.CONF

CONF.import_opt('api_version',
                'nova.virt.ironic.driver',
                group='ironic')
CONF.import_opt('api_endpoint',
                'nova.virt.ironic.driver',
                group='ironic')
CONF.import_opt('admin_username',
                'nova.virt.ironic.driver',
                group='ironic')
CONF.import_opt('admin_password',
                'nova.virt.ironic.driver',
                group='ironic')
CONF.import_opt('admin_tenant_name',
                'nova.virt.ironic.driver',
                group='ironic')
CONF.import_opt('compute_driver', 'nova.virt.driver')

LOG = logging.getLogger(__name__)


def _interface_dict(interface_ref):
    d = {}
    for f in interface_fields:
        d[f] = interface_ref.get(f)
    return d


def _make_node_elem(elem):
    for f in node_fields:
        elem.set(f)
    for f in node_ext_fields:
        elem.set(f)


def _make_interface_elem(elem):
    for f in interface_fields:
        elem.set(f)


def _use_ironic():
    # TODO(lucasagomes): This switch this should also be deleted as
    # part of the Nova Baremetal removal effort. At that point, any
    # code that checks it should assume True, the False case should be
    # removed, and this API will only/always proxy to Ironic.
    return 'ironic' in CONF.compute_driver


def _get_ironic_client():
    """return an Ironic client."""
    # TODO(NobodyCam): Fix insecure setting
    kwargs = {'os_username': CONF.ironic.admin_username,
              'os_password': CONF.ironic.admin_password,
              'os_auth_url': CONF.ironic.admin_url,
              'os_tenant_name': CONF.ironic.admin_tenant_name,
              'os_service_type': 'baremetal',
              'os_endpoint_type': 'public',
              'insecure': 'true',
              'ironic_url': CONF.ironic.api_endpoint}
    icli = ironic_client.get_client(CONF.ironic.api_version, **kwargs)
    return icli


def _no_ironic_proxy(cmd):
    raise webob.exc.HTTPBadRequest(
                    explanation=_("Command Not supported. Please use Ironic "
                                  "command %(cmd)s to perform this "
                                  "action.") % {'cmd': cmd})


def is_valid_mac(address):
    """Verify the format of a MAC address."""

    class mac_dialect(netaddr.mac_eui48):
        word_fmt = '%.02x'
        word_sep = ':'

    try:
        na = netaddr.EUI(address, dialect=mac_dialect)
    except Exception:
        return False
    return str(na) == address.lower()


class NodeTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        node_elem = xmlutil.TemplateElement('node', selector='node')
        _make_node_elem(node_elem)
        ifs_elem = xmlutil.TemplateElement('interfaces')
        if_elem = xmlutil.SubTemplateElement(ifs_elem, 'interface',
                                             selector='interfaces')
        _make_interface_elem(if_elem)
        node_elem.append(ifs_elem)
        return xmlutil.MasterTemplate(node_elem, 1)


class NodesTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('nodes')
        node_elem = xmlutil.SubTemplateElement(root, 'node', selector='nodes')
        _make_node_elem(node_elem)
        ifs_elem = xmlutil.TemplateElement('interfaces')
        if_elem = xmlutil.SubTemplateElement(ifs_elem, 'interface',
                                             selector='interfaces')
        _make_interface_elem(if_elem)
        node_elem.append(ifs_elem)
        return xmlutil.MasterTemplate(root, 1)


class InterfaceTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('interface', selector='interface')
        _make_interface_elem(root)
        return xmlutil.MasterTemplate(root, 1)


class BareMetalNodeController(wsgi.Controller):
    """The Bare-Metal Node API controller for the OpenStack API.

    Ironic is used for the following commands:
        'baremetal-node-list'
        'baremetal-node-show'
    """

    def __init__(self, ext_mgr=None, *args, **kwargs):
        super(BareMetalNodeController, self).__init__(*args, **kwargs)
        self.ext_mgr = ext_mgr

    def _node_dict(self, node_ref):
        d = {}
        for f in node_fields:
            d[f] = node_ref.get(f)
        if self.ext_mgr.is_loaded('os-baremetal-ext-status'):
            for f in node_ext_fields:
                d[f] = node_ref.get(f)
        return d

    @wsgi.serializers(xml=NodesTemplate)
    def index(self, req):
        context = req.environ['nova.context']
        authorize(context)
        nodes = []
        if _use_ironic():
            # proxy command to Ironic
            icli = _get_ironic_client()
            ironic_nodes = icli.node.list(detail=True)
            for inode in ironic_nodes:
                node = {'id': inode.uuid,
                        'interfaces': [],
                        'host': 'IRONIC MANAGED',
                        'task_state': inode.provision_state,
                        'cpus': inode.properties['cpus'],
                        'memory_mb': inode.properties['memory_mb'],
                        'disk_gb': inode.properties['local_gb']}
                nodes.append(node)
        else:
            # use nova baremetal
            nodes_from_db = db.bm_node_get_all(context)
            for node_from_db in nodes_from_db:
                try:
                    ifs = db.bm_interface_get_all_by_bm_node_id(
                            context, node_from_db['id'])
                except exception.NodeNotFound:
                    ifs = []
                node = self._node_dict(node_from_db)
                node['interfaces'] = [_interface_dict(i) for i in ifs]
                nodes.append(node)
        return {'nodes': nodes}

    @wsgi.serializers(xml=NodeTemplate)
    def show(self, req, id):
        context = req.environ['nova.context']
        authorize(context)
        if _use_ironic():
            # proxy command to Ironic
            icli = _get_ironic_client()
            inode = icli.node.get(id)
            iports = icli.node.list_ports(id)
            node = {'id': inode.uuid,
                    'interfaces': [],
                    'host': 'IRONIC MANAGED',
                    'task_state': inode.provision_state,
                    'cpus': inode.properties['cpus'],
                    'memory_mb': inode.properties['memory_mb'],
                    'disk_gb': inode.properties['local_gb'],
                    'instance_uuid': inode.instance_uuid}
            for port in iports:
                node['interfaces'].append({'address': port.address})
        else:
            # use nova baremetal
            try:
                node = db.bm_node_get(context, id)
            except exception.NodeNotFound:
                raise webob.exc.HTTPNotFound()
            try:
                ifs = db.bm_interface_get_all_by_bm_node_id(context, id)
            except exception.NodeNotFound:
                ifs = []
            node = self._node_dict(node)
            node['interfaces'] = [_interface_dict(i) for i in ifs]
        return {'node': node}

    @wsgi.serializers(xml=NodeTemplate)
    def create(self, req, body):
        if _use_ironic():
            _no_ironic_proxy("node-create")

        context = req.environ['nova.context']
        authorize(context)
        values = body['node'].copy()
        prov_mac_address = values.pop('prov_mac_address', None)
        if (prov_mac_address is not None
                and not is_valid_mac(prov_mac_address)):
            raise webob.exc.HTTPBadRequest(
                    explanation=_("Must specify address "
                                  "in the form of xx:xx:xx:xx:xx:xx"))
        node = db.bm_node_create(context, values)
        node = self._node_dict(node)
        if prov_mac_address:
            if_id = db.bm_interface_create(context,
                                           bm_node_id=node['id'],
                                           address=prov_mac_address,
                                           datapath_id=None,
                                           port_no=None)
            if_ref = db.bm_interface_get(context, if_id)
            node['interfaces'] = [_interface_dict(if_ref)]
        else:
            node['interfaces'] = []
        return {'node': node}

    def delete(self, req, id):
        if _use_ironic():
            _no_ironic_proxy("node-delete")

        context = req.environ['nova.context']
        authorize(context)
        try:
            db.bm_node_destroy(context, id)
        except exception.NodeNotFound:
            raise webob.exc.HTTPNotFound()
        return webob.Response(status_int=202)

    def _check_node_exists(self, context, node_id):
        try:
            db.bm_node_get(context, node_id)
        except exception.NodeNotFound:
            raise webob.exc.HTTPNotFound()

    @wsgi.serializers(xml=InterfaceTemplate)
    @wsgi.action('add_interface')
    def _add_interface(self, req, id, body):
        if _use_ironic():
            _no_ironic_proxy("port-create")

        context = req.environ['nova.context']
        authorize(context)
        self._check_node_exists(context, id)
        body = body['add_interface']
        address = body['address']
        datapath_id = body.get('datapath_id')
        port_no = body.get('port_no')
        if not is_valid_mac(address):
            raise webob.exc.HTTPBadRequest(
                    explanation=_("Must specify address "
                                  "in the form of xx:xx:xx:xx:xx:xx"))
        if_id = db.bm_interface_create(context,
                                       bm_node_id=id,
                                       address=address,
                                       datapath_id=datapath_id,
                                       port_no=port_no)
        if_ref = db.bm_interface_get(context, if_id)
        return {'interface': _interface_dict(if_ref)}

    @wsgi.response(202)
    @wsgi.action('remove_interface')
    def _remove_interface(self, req, id, body):
        if _use_ironic():
            _no_ironic_proxy("port-delete")

        context = req.environ['nova.context']
        authorize(context)
        self._check_node_exists(context, id)
        body = body['remove_interface']
        if_id = body.get('id')
        address = body.get('address')
        if not if_id and not address:
            raise webob.exc.HTTPBadRequest(
                    explanation=_("Must specify id or address"))
        ifs = db.bm_interface_get_all_by_bm_node_id(context, id)
        for i in ifs:
            if if_id and if_id != i['id']:
                continue
            if address and address != i['address']:
                continue
            db.bm_interface_destroy(context, i['id'])
            return webob.Response(status_int=202)
        raise webob.exc.HTTPNotFound()


class Baremetal_nodes(extensions.ExtensionDescriptor):
    """Admin-only bare-metal node administration."""

    name = "BareMetalNodes"
    alias = "os-baremetal-nodes"
    namespace = "http://docs.openstack.org/compute/ext/baremetal_nodes/api/v2"
    updated = "2013-01-04T00:00:00Z"

    def get_resources(self):
        resources = []
        res = extensions.ResourceExtension('os-baremetal-nodes',
                BareMetalNodeController(self.ext_mgr),
                member_actions={"action": "POST", })
        resources.append(res)
        return resources
