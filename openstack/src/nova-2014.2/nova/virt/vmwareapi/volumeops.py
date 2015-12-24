# Copyright (c) 2013 Hewlett-Packard Development Company, L.P.
# Copyright (c) 2012 VMware, Inc.
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

"""
Management class for Storage-related functions (attach, detach, etc).
"""

from oslo.config import cfg

from nova import exception
from nova.i18n import _
from nova.openstack.common import log as logging
from nova.virt.vmwareapi import vim_util
from nova.virt.vmwareapi import vm_util

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class VMwareVolumeOps(object):
    """Management class for Volume-related tasks."""

    def __init__(self, session, cluster=None):
        self._session = session
        self._cluster = cluster

    def attach_disk_to_vm(self, vm_ref, instance,
                          adapter_type, disk_type, vmdk_path=None,
                          disk_size=None, linked_clone=False,
                          device_name=None):
        """Attach disk to VM by reconfiguration."""
        instance_name = instance['name']
        client_factory = self._session._get_vim().client.factory
        devices = self._session._call_method(vim_util,
                                    "get_dynamic_property", vm_ref,
                                    "VirtualMachine", "config.hardware.device")
        (controller_key, unit_number,
         controller_spec) = vm_util.allocate_controller_key_and_unit_number(
                                                              client_factory,
                                                              devices,
                                                              adapter_type)

        vmdk_attach_config_spec = vm_util.get_vmdk_attach_config_spec(
                                    client_factory, disk_type, vmdk_path,
                                    disk_size, linked_clone, controller_key,
                                    unit_number, device_name)
        if controller_spec:
            vmdk_attach_config_spec.deviceChange.append(controller_spec)

        LOG.debug("Reconfiguring VM instance %(instance_name)s to attach "
                  "disk %(vmdk_path)s or device %(device_name)s with type "
                  "%(disk_type)s",
                  {'instance_name': instance_name, 'vmdk_path': vmdk_path,
                   'device_name': device_name, 'disk_type': disk_type},
                  instance=instance)
        vm_util.reconfigure_vm(self._session, vm_ref, vmdk_attach_config_spec)
        LOG.debug("Reconfigured VM instance %(instance_name)s to attach "
                  "disk %(vmdk_path)s or device %(device_name)s with type "
                  "%(disk_type)s",
                  {'instance_name': instance_name, 'vmdk_path': vmdk_path,
                   'device_name': device_name, 'disk_type': disk_type},
                  instance=instance)

    def _update_volume_details(self, vm_ref, instance, volume_uuid):
        # Store the uuid of the volume_device
        hw_devices = self._session._call_method(vim_util,
                                                'get_dynamic_property',
                                                vm_ref, 'VirtualMachine',
                                                'config.hardware.device')
        device_uuid = vm_util.get_vmdk_backed_disk_uuid(hw_devices,
                                                        volume_uuid)
        volume_option = 'volume-%s' % volume_uuid
        extra_opts = {volume_option: device_uuid}

        client_factory = self._session._get_vim().client.factory
        extra_config_specs = vm_util.get_vm_extra_config_spec(
                                    client_factory, extra_opts)
        vm_util.reconfigure_vm(self._session, vm_ref, extra_config_specs)

    def _get_volume_uuid(self, vm_ref, volume_uuid):
        prop = 'config.extraConfig["volume-%s"]' % volume_uuid
        opt_val = self._session._call_method(vim_util,
                                             'get_dynamic_property',
                                             vm_ref, 'VirtualMachine',
                                             prop)
        if opt_val is not None:
            return opt_val.value

    def detach_disk_from_vm(self, vm_ref, instance, device,
                            destroy_disk=False):
        """Detach disk from VM by reconfiguration."""
        instance_name = instance['name']
        client_factory = self._session._get_vim().client.factory
        vmdk_detach_config_spec = vm_util.get_vmdk_detach_config_spec(
                                    client_factory, device, destroy_disk)
        disk_key = device.key
        LOG.debug("Reconfiguring VM instance %(instance_name)s to detach "
                  "disk %(disk_key)s",
                  {'instance_name': instance_name, 'disk_key': disk_key},
                  instance=instance)
        vm_util.reconfigure_vm(self._session, vm_ref, vmdk_detach_config_spec)
        LOG.debug("Reconfigured VM instance %(instance_name)s to detach "
                  "disk %(disk_key)s",
                  {'instance_name': instance_name, 'disk_key': disk_key},
                  instance=instance)

    def _iscsi_get_target(self, data):
        """Return the iSCSI Target given a volume info."""
        target_portal = data['target_portal']
        target_iqn = data['target_iqn']
        host_mor = vm_util.get_host_ref(self._session, self._cluster)

        lst_properties = ["config.storageDevice.hostBusAdapter",
                          "config.storageDevice.scsiTopology",
                          "config.storageDevice.scsiLun"]
        prop_dict = self._session._call_method(
            vim_util, "get_dynamic_properties",
            host_mor, "HostSystem", lst_properties)
        result = (None, None)
        hbas_ret = None
        scsi_topology = None
        scsi_lun_ret = None
        if prop_dict:
            hbas_ret = prop_dict.get('config.storageDevice.hostBusAdapter')
            scsi_topology = prop_dict.get('config.storageDevice.scsiTopology')
            scsi_lun_ret = prop_dict.get('config.storageDevice.scsiLun')

        # Meaning there are no host bus adapters on the host
        if hbas_ret is None:
            return result
        host_hbas = hbas_ret.HostHostBusAdapter
        if not host_hbas:
            return result
        for hba in host_hbas:
            if hba.__class__.__name__ == 'HostInternetScsiHba':
                hba_key = hba.key
                break
        else:
            return result

        if scsi_topology is None:
            return result
        host_adapters = scsi_topology.adapter
        if not host_adapters:
            return result
        scsi_lun_key = None
        for adapter in host_adapters:
            if adapter.adapter == hba_key:
                if not getattr(adapter, 'target', None):
                    return result
                for target in adapter.target:
                    if (getattr(target.transport, 'address', None) and
                        target.transport.address[0] == target_portal and
                            target.transport.iScsiName == target_iqn):
                        if not target.lun:
                            return result
                        for lun in target.lun:
                            if 'host.ScsiDisk' in lun.scsiLun:
                                scsi_lun_key = lun.scsiLun
                                break
                        break
                break

        if scsi_lun_key is None:
            return result

        if scsi_lun_ret is None:
            return result
        host_scsi_luns = scsi_lun_ret.ScsiLun
        if not host_scsi_luns:
            return result
        for scsi_lun in host_scsi_luns:
            if scsi_lun.key == scsi_lun_key:
                return (scsi_lun.deviceName, scsi_lun.uuid)

        return result

    def _iscsi_add_send_target_host(self, storage_system_mor, hba_device,
                                    target_portal):
        """Adds the iscsi host to send target host list."""
        client_factory = self._session._get_vim().client.factory
        send_tgt = client_factory.create('ns0:HostInternetScsiHbaSendTarget')
        (send_tgt.address, send_tgt.port) = target_portal.split(':')
        LOG.debug("Adding iSCSI host %s to send targets", send_tgt.address)
        self._session._call_method(
            self._session._get_vim(), "AddInternetScsiSendTargets",
            storage_system_mor, iScsiHbaDevice=hba_device, targets=[send_tgt])

    def _iscsi_rescan_hba(self, target_portal):
        """Rescan the iSCSI HBA to discover iSCSI targets."""
        host_mor = vm_util.get_host_ref(self._session, self._cluster)
        storage_system_mor = self._session._call_method(
            vim_util, "get_dynamic_property",
            host_mor, "HostSystem",
            "configManager.storageSystem")
        hbas_ret = self._session._call_method(
            vim_util, "get_dynamic_property",
            storage_system_mor, "HostStorageSystem",
            "storageDeviceInfo.hostBusAdapter")
        # Meaning there are no host bus adapters on the host
        if hbas_ret is None:
            return
        host_hbas = hbas_ret.HostHostBusAdapter
        if not host_hbas:
            return
        for hba in host_hbas:
            if hba.__class__.__name__ == 'HostInternetScsiHba':
                hba_device = hba.device
                if target_portal:
                    # Check if iscsi host is already in the send target host
                    # list
                    send_targets = getattr(hba, 'configuredSendTarget', [])
                    send_tgt_portals = ['%s:%s' % (s.address, s.port) for s in
                                        send_targets]
                    if target_portal not in send_tgt_portals:
                        self._iscsi_add_send_target_host(storage_system_mor,
                                                         hba_device,
                                                         target_portal)
                break
        else:
            return
        LOG.debug("Rescanning HBA %s", hba_device)
        self._session._call_method(self._session._get_vim(),
            "RescanHba", storage_system_mor, hbaDevice=hba_device)
        LOG.debug("Rescanned HBA %s ", hba_device)

    def _iscsi_discover_target(self, data):
        """Get iSCSI target, rescanning the HBA if necessary."""
        target_portal = data['target_portal']
        target_iqn = data['target_iqn']
        LOG.debug("Discovering iSCSI target %(target_iqn)s from "
                  "%(target_portal)s.",
                  {'target_iqn': target_iqn, 'target_portal': target_portal})
        device_name, uuid = self._iscsi_get_target(data)
        if device_name:
            LOG.debug("Storage target found. No need to discover")
            return (device_name, uuid)

        # Rescan iSCSI HBA with iscsi target host
        self._iscsi_rescan_hba(target_portal)

        # Find iSCSI Target again
        device_name, uuid = self._iscsi_get_target(data)
        if device_name:
            LOG.debug("Discovered iSCSI target %(target_iqn)s from "
                      "%(target_portal)s.",
                      {'target_iqn': target_iqn,
                       'target_portal': target_portal})
        else:
            LOG.debug("Unable to discovered iSCSI target %(target_iqn)s "
                      "from %(target_portal)s.",
                      {'target_iqn': target_iqn,
                       'target_portal': target_portal})
        return (device_name, uuid)

    def _iscsi_get_host_iqn(self):
        """Return the host iSCSI IQN."""
        host_mor = vm_util.get_host_ref(self._session, self._cluster)
        hbas_ret = self._session._call_method(
            vim_util, "get_dynamic_property",
            host_mor, "HostSystem",
            "config.storageDevice.hostBusAdapter")

        # Meaning there are no host bus adapters on the host
        if hbas_ret is None:
            return
        host_hbas = hbas_ret.HostHostBusAdapter
        if not host_hbas:
            return
        for hba in host_hbas:
            if hba.__class__.__name__ == 'HostInternetScsiHba':
                return hba.iScsiName

    def get_volume_connector(self, instance):
        """Return volume connector information."""
        try:
            vm_ref = vm_util.get_vm_ref(self._session, instance)
        except exception.InstanceNotFound:
            vm_ref = None
        iqn = self._iscsi_get_host_iqn()
        connector = {'ip': CONF.vmware.host_ip,
                     'initiator': iqn,
                     'host': CONF.vmware.host_ip}
        if vm_ref:
            connector['instance'] = vm_ref.value
        return connector

    def _get_volume_ref(self, volume_ref_name):
        """Get the volume moref from the ref name."""
        return vim_util.get_moref(volume_ref_name, 'VirtualMachine')

    def _get_vmdk_base_volume_device(self, volume_ref):
        # Get the vmdk file name that the VM is pointing to
        hardware_devices = self._session._call_method(vim_util,
                        "get_dynamic_property", volume_ref,
                        "VirtualMachine", "config.hardware.device")
        return vm_util.get_vmdk_volume_disk(hardware_devices)

    def _attach_volume_vmdk(self, connection_info, instance, mountpoint):
        """Attach vmdk volume storage to VM instance."""
        instance_name = instance['name']
        vm_ref = vm_util.get_vm_ref(self._session, instance)
        data = connection_info['data']

        # Get volume details from volume ref
        volume_ref = self._get_volume_ref(data['volume'])
        volume_device = self._get_vmdk_base_volume_device(volume_ref)
        volume_vmdk_path = volume_device.backing.fileName

        # Get details required for adding disk device such as
        # adapter_type, disk_type
        hw_devices = self._session._call_method(vim_util,
                                                'get_dynamic_property',
                                                vm_ref, 'VirtualMachine',
                                                'config.hardware.device')
        (vmdk_file_path, adapter_type,
         disk_type) = vm_util.get_vmdk_path_and_adapter_type(hw_devices)

        # Attach the disk to virtual machine instance
        self.attach_disk_to_vm(vm_ref, instance, adapter_type,
                               disk_type, vmdk_path=volume_vmdk_path)

        # Store the uuid of the volume_device
        self._update_volume_details(vm_ref, instance, data['volume_id'])

        LOG.info(_("Mountpoint %(mountpoint)s attached to "
                   "instance %(instance_name)s"),
                 {'mountpoint': mountpoint, 'instance_name': instance_name},
                 instance=instance)

    def _attach_volume_iscsi(self, connection_info, instance, mountpoint):
        """Attach iscsi volume storage to VM instance."""
        instance_name = instance['name']
        vm_ref = vm_util.get_vm_ref(self._session, instance)
        # Attach Volume to VM
        LOG.debug("Attach_volume: %(connection_info)s, %(instance_name)s, "
                  "%(mountpoint)s",
                  {'connection_info': connection_info,
                   'instance_name': instance_name,
                   'mountpoint': mountpoint},
                  instance=instance)

        data = connection_info['data']

        # Discover iSCSI Target
        device_name = self._iscsi_discover_target(data)[0]
        if device_name is None:
            raise exception.StorageError(
                reason=_("Unable to find iSCSI Target"))

        # Get the vmdk file name that the VM is pointing to
        hardware_devices = self._session._call_method(vim_util,
                        "get_dynamic_property", vm_ref,
                        "VirtualMachine", "config.hardware.device")
        (vmdk_file_path, adapter_type,
         disk_type) = vm_util.get_vmdk_path_and_adapter_type(hardware_devices)

        self.attach_disk_to_vm(vm_ref, instance,
                               adapter_type, 'rdmp',
                               device_name=device_name)
        LOG.info(_("Mountpoint %(mountpoint)s attached to "
                   "instance %(instance_name)s"),
                 {'mountpoint': mountpoint, 'instance_name': instance_name},
                 instance=instance)

    def attach_volume(self, connection_info, instance, mountpoint):
        """Attach volume storage to VM instance."""
        driver_type = connection_info['driver_volume_type']
        LOG.debug("Volume attach. Driver type: %s", driver_type,
                  instance=instance)
        if driver_type == 'vmdk':
            self._attach_volume_vmdk(connection_info, instance, mountpoint)
        elif driver_type == 'iscsi':
            self._attach_volume_iscsi(connection_info, instance, mountpoint)
        else:
            raise exception.VolumeDriverNotFound(driver_type=driver_type)

    def _relocate_vmdk_volume(self, volume_ref, res_pool, datastore):
        """Relocate the volume.

        The move type will be moveAllDiskBackingsAndAllowSharing.
        """
        client_factory = self._session._get_vim().client.factory
        spec = vm_util.relocate_vm_spec(client_factory,
                                        datastore=datastore)
        spec.pool = res_pool
        task = self._session._call_method(self._session._get_vim(),
                                          "RelocateVM_Task", volume_ref,
                                          spec=spec)
        self._session._wait_for_task(task)

    def _get_res_pool_of_vm(self, vm_ref):
        """Get resource pool to which the VM belongs."""
        # Get the host, the VM belongs to
        host = self._session._call_method(vim_util, 'get_dynamic_property',
                                          vm_ref, 'VirtualMachine',
                                          'runtime').host
        # Get the compute resource, the host belongs to
        compute_res = self._session._call_method(vim_util,
                                                 'get_dynamic_property',
                                                 host, 'HostSystem',
                                                 'parent')
        # Get resource pool from the compute resource
        return self._session._call_method(vim_util, 'get_dynamic_property',
                                          compute_res, compute_res._type,
                                          'resourcePool')

    def _consolidate_vmdk_volume(self, instance, vm_ref, device, volume_ref):
        """Consolidate volume backing VMDK files if needed.

        The volume's VMDK file attached to an instance can be moved by SDRS
        if enabled on the cluster.
        By this the VMDK files can get copied onto another datastore and the
        copy on this new location will be the latest version of the VMDK file.
        So at the time of detach, we need to consolidate the current backing
        VMDK file with the VMDK file in the new location.

        We need to ensure that the VMDK chain (snapshots) remains intact during
        the consolidation. SDRS retains the chain when it copies VMDK files
        over, so for consolidation we relocate the backing with move option
        as moveAllDiskBackingsAndAllowSharing and then delete the older version
        of the VMDK file attaching the new version VMDK file.

        In the case of a volume boot the we need to ensure that the volume
        is on the datastore of the instance.
        """

        original_device = self._get_vmdk_base_volume_device(volume_ref)

        original_device_path = original_device.backing.fileName
        current_device_path = device.backing.fileName

        if original_device_path == current_device_path:
            # The volume is not moved from its original location.
            # No consolidation is required.
            LOG.debug("The volume has not been displaced from "
                      "its original location: %s. No consolidation "
                      "needed.", current_device_path)
            return

        # The volume has been moved from its original location.
        # Need to consolidate the VMDK files.
        LOG.info(_("The volume's backing has been relocated to %s. Need to "
                   "consolidate backing disk file."), current_device_path)

        # Pick the resource pool on which the instance resides.
        # Move the volume to the datastore where the new VMDK file is present.
        res_pool = self._get_res_pool_of_vm(vm_ref)
        datastore = device.backing.datastore
        self._relocate_vmdk_volume(volume_ref, res_pool, datastore)

        # Delete the original disk from the volume_ref
        self.detach_disk_from_vm(volume_ref, instance, original_device,
                                 destroy_disk=True)
        # Attach the current disk to the volume_ref
        # Get details required for adding disk device such as
        # adapter_type, disk_type
        hw_devices = self._session._call_method(vim_util,
                                                'get_dynamic_property',
                                                volume_ref, 'VirtualMachine',
                                                'config.hardware.device')
        (vmdk_file_path, adapter_type,
         disk_type) = vm_util.get_vmdk_path_and_adapter_type(hw_devices)
        # Attach the current volume to the volume_ref
        self.attach_disk_to_vm(volume_ref, instance,
                               adapter_type, disk_type,
                               vmdk_path=current_device_path)

    def _get_vmdk_backed_disk_device(self, vm_ref, connection_info_data):
        # Get the vmdk file name that the VM is pointing to
        hardware_devices = self._session._call_method(vim_util,
                        "get_dynamic_property", vm_ref,
                        "VirtualMachine", "config.hardware.device")

        # Get disk uuid
        disk_uuid = self._get_volume_uuid(vm_ref,
                                          connection_info_data['volume_id'])
        device = vm_util.get_vmdk_backed_disk_device(hardware_devices,
                                                     disk_uuid)
        if not device:
            raise exception.StorageError(reason=_("Unable to find volume"))
        return device

    def _detach_volume_vmdk(self, connection_info, instance, mountpoint):
        """Detach volume storage to VM instance."""
        instance_name = instance['name']
        vm_ref = vm_util.get_vm_ref(self._session, instance)
        # Detach Volume from VM
        LOG.debug("Detach_volume: %(instance_name)s, %(mountpoint)s",
                  {'mountpoint': mountpoint, 'instance_name': instance_name},
                  instance=instance)
        data = connection_info['data']

        device = self._get_vmdk_backed_disk_device(vm_ref, data)

        # Get the volume ref
        volume_ref = self._get_volume_ref(data['volume'])
        self._consolidate_vmdk_volume(instance, vm_ref, device, volume_ref)

        self.detach_disk_from_vm(vm_ref, instance, device)
        LOG.info(_("Mountpoint %(mountpoint)s detached from "
                   "instance %(instance_name)s"),
                 {'mountpoint': mountpoint, 'instance_name': instance_name},
                 instance=instance)

    def _detach_volume_iscsi(self, connection_info, instance, mountpoint):
        """Detach volume storage to VM instance."""
        instance_name = instance['name']
        vm_ref = vm_util.get_vm_ref(self._session, instance)
        # Detach Volume from VM
        LOG.debug("Detach_volume: %(instance_name)s, %(mountpoint)s",
                  {'mountpoint': mountpoint, 'instance_name': instance_name},
                  instance=instance)
        data = connection_info['data']

        # Discover iSCSI Target
        device_name, uuid = self._iscsi_get_target(data)
        if device_name is None:
            raise exception.StorageError(
                reason=_("Unable to find iSCSI Target"))

        # Get the vmdk file name that the VM is pointing to
        hardware_devices = self._session._call_method(vim_util,
                        "get_dynamic_property", vm_ref,
                        "VirtualMachine", "config.hardware.device")
        device = vm_util.get_rdm_disk(hardware_devices, uuid)
        if device is None:
            raise exception.StorageError(reason=_("Unable to find volume"))
        self.detach_disk_from_vm(vm_ref, instance, device, destroy_disk=True)
        LOG.info(_("Mountpoint %(mountpoint)s detached from "
                   "instance %(instance_name)s"),
                 {'mountpoint': mountpoint, 'instance_name': instance_name},
                 instance=instance)

    def detach_volume(self, connection_info, instance, mountpoint):
        """Detach volume storage to VM instance."""
        driver_type = connection_info['driver_volume_type']
        LOG.debug("Volume detach. Driver type: %s", driver_type,
                  instance=instance)
        if driver_type == 'vmdk':
            self._detach_volume_vmdk(connection_info, instance, mountpoint)
        elif driver_type == 'iscsi':
            self._detach_volume_iscsi(connection_info, instance, mountpoint)
        else:
            raise exception.VolumeDriverNotFound(driver_type=driver_type)

    def attach_root_volume(self, connection_info, instance, mountpoint,
                           datastore):
        """Attach a root volume to the VM instance."""
        driver_type = connection_info['driver_volume_type']
        LOG.debug("Root volume attach. Driver type: %s", driver_type,
                  instance=instance)
        if driver_type == 'vmdk':
            vm_ref = vm_util.get_vm_ref(self._session, instance)
            data = connection_info['data']
            # Get the volume ref
            volume_ref = self._get_volume_ref(data['volume'])
            # Pick the resource pool on which the instance resides. Move the
            # volume to the datastore of the instance.
            res_pool = self._get_res_pool_of_vm(vm_ref)
            self._relocate_vmdk_volume(volume_ref, res_pool, datastore)

        self.attach_volume(connection_info, instance, mountpoint)
