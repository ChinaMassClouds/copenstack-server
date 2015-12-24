from openstack_dashboard import api
from django.utils.text import normalize_newlines
import logging
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from novaclient.v1_1 import client as nova_client

LOG = logging.getLogger(__name__)

def create():
        with open('/tmp/a','r') as f:
            data = f.read()
        undata = data.split(' ')
        image_id=undata[0]
        context = eval(undata[1])
        tt=undata[2]
        custom_script = context.get('script_data', '')
        if source_type in ['volume_id', 'volume_snapshot_id']:
            dev_mapping_1 = {context['device_name']: '%s::%s' %
                                                     (context['source_id'],
                           int(bool(context['delete_on_terminate'])))}
        elif source_type == 'volume_image_id':
            dev_mapping_2 = [
                {'device_name': str(context['device_name']),
                 'source_type': 'image',
                 'destination_type': 'volume',
                 'delete_on_termination':
                     int(bool(context['delete_on_terminate'])),
                 'uuid': context['source_id'],
                 'boot_index': '0',
                 'volume_size': context['volume_size']
                 }
            ]

        netids = context.get('network_id', None)
        if netids:
            nics = [{"net-id": netid, "v4-fixed-ip": ""}
                    for netid in netids]
        else:
            nics = None

        avail_zone = context.get('availability_zone', None)

        if api.neutron.is_port_profiles_supported():
            net_id = context['network_id'][0]
            LOG.debug("Horizon->Create Port with %(netid)s %(profile_id)s",
                      {'netid': net_id, 'profile_id': context['profile_id']})
           # port = None
           # try:
           #     port = api.neutron.port_create(
           #         request, net_id, policy_profile_id=context['profile_id'])
           # except Exception:
           #     msg = (_('Port not created for profile-id (%s).') %
           #            context['profile_id'])
               # exceptions.handle(request, msg)

            if port and port.id:
                nics = [{"port-id": port.id}]

        try:
            """
            api.nova.server_create(request,
                                   context['name'],
                                   image_id,
                                   context['flavor'],
                                   context['keypair_id'],
                                   normalize_newlines(custom_script),
                                   context['security_group_ids'],
                                   block_device_mapping=dev_mapping_1,
                                   block_device_mapping_v2=dev_mapping_2,
                                   nics=nics,
                                   availability_zone=avail_zone,
                                   instance_count=int(context['count']),
                                   admin_pass=context['admin_pass'],
                                   disk_config=context.get('disk_config'),
                                   config_drive=context.get('config_drive'))
                                   """


            novaclient('/tmp/b').servers.create(
        context['name'], image_id, context['flavor'], userdata=normalize_newlines(custom_script),
        security_groups=context['security_group_ids'],
        key_name=context['keypair_id'], block_device_mapping=dev_mapping_1,
        block_device_mapping_v2=dev_mapping_2,
        nics=nics, availability_zone=avail_zone,
        min_count=int(context['count']), admin_pass=context['admin_pass'],
        disk_config=context.get('disk_config'), config_drive=context.get('config_drive'),
        meta=None)
            return True
        except Exception:
    #       exceptions.handle(request)
            return False


def novaclient(file):
    with open(file,'r') as f:
        data = eval(f.read())
    insecure = getattr(settings, 'OPENSTACK_SSL_NO_VERIFY', False)
    cacert = getattr(settings, 'OPENSTACK_SSL_CACERT', None)
    c = nova_client.Client(data['name'],
                           data['token'],
                           project_id=data['project_id'],
                           auth_url=data['url'],
                           insecure=insecure,
                           cacert=cacert,
                           http_log_debug=settings.DEBUG)
    return c

create()
