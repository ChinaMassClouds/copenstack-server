#coding:utf-8

from platforms.vcenter.session import VMwareAPISession
from exception import LoginVCenterFailed
from platforms.vcenter.vcenterplatform import VCenterPlatformInstanceInfo
import uuid, json
from db.mysql import NovaDatabase, PlatformDatabase
from db.common import NovaDBConfig, VCenterDBConfig
from base import PlatformManager
import os

class VCenterPlatformManager(PlatformManager):
    """
    vcenter平台管理类
    """
    _ptype = "vcenter"
    def __init__(self):
        super(VCenterPlatformManager, self).__init__()

    
    def create_platform_info_obj(self, instance_info):
        """
        创建vcenter实例信息对象
        """
        try:
            session = VMwareAPISession(instance_info["virtualplatformIP"], \
                                       instance_info["virtualplatformusername"], \
                                       instance_info["virtualplatformpassword"])
        except Exception:
            raise LoginVCenterFailed()
        
        uuidv = instance_info.get("uuid", None)
        dc_cluster = instance_info.get("datacentersandclusters", None)
        vc_instance = VCenterPlatformInstanceInfo(instance_info["name"], \
                                                  instance_info["domain_name"], \
                                                  instance_info["hostname"], \
                                                  instance_info["virtualplatformtype"], \
                                                  uuidv, session, \
                                                  instance_info["virtualplatformIP"], \
                                                  instance_info["virtualplatformusername"], \
                                                  instance_info["virtualplatformpassword"], \
                                                  dc_cluster)
        return vc_instance
    
    def add_vcenter_platform_instance(self, instance_info):
        """
        添加vcenter平台实例
        _@instance_info:平台实例的基础信息,集群的用户名，密码和地址信息，接管集群等
        """
        cluster_list = []
        cluster_str = ""
        username = instance_info["virtualplatformusername"]
        password = instance_info["virtualplatformpassword"]
        ip = instance_info["virtualplatformIP"]
        
        dc_cluster = instance_info["datacentersandclusters"]
        for dc in dc_cluster:
            for cluster in dc_cluster[dc]:
                cluster_list.append(cluster)
        
        for cluster in cluster_list:
            cluster_str += "cluster_name = %s\\n" % cluster
            
        if cluster_str:
            cluster_str = cluster_str[0:-2]
        
        vcenter_cfg_cmd = "sed -i \"/^\[vmware\]$/a host_password = %s \\nhost_username = %s\\nhost_ip = %s\\n%s\" /etc/nova/nova.conf " \
                     % (password, username, ip, cluster_str)
                     
        cinder_cfg_cmd = "sed -i \"/^\[DEFAULT\]$/a volume_driver = cinder.volume.drivers.vmware.vmdk.VMwareVcVmdkDriver\
\\nvmware_host_password = %s\\nvmware_host_username = %s\
\\nvmware_host_ip = %s\\nvmware_volume_folder = cinder-volumes\
\\nvmware_host_version = 5.5\" /etc/cinder/cinder.conf " \
                                % (password, username, ip)
               
        ceilometer_cfg_cmd = "sed -i \"/^\[vmware\]$/a host_password = %s \\nhost_username = %s\\nhost_ip = %s\\n%s\" \
                                  /etc/ceilometer/ceilometer.conf " % (password, username, ip, cluster_str)
                     
        """配置/etc/nova/nova.conf中的计算服务的驱动为vcenter类型"""
        cmd_list = [
                    "sed -i '/^hypervisor_inspector/d' /etc/ceilometer/ceilometer.conf",
                    "sed -i '/^host_ip/d' /etc/cinder/cinder.conf",
                    "sed -i '/^host_username/d' /etc/cinder/cinder.conf",
                    "sed -i '/^host_password/d' /etc/cinder/cinder.conf",
                    "sed -i \"/^\[DEFAULT\]$/a hypervisor_inspector = vsphere\" /etc/ceilometer/ceilometer.conf",
                    ceilometer_cfg_cmd,
                    "sed -i '/^volume_driver/d' /etc/cinder/cinder.conf",
                    "sed -i '/^vmware_host_password/d' /etc/cinder/cinder.conf",
                    "sed -i '/^vmware_host_username/d' /etc/cinder/cinder.conf",
                    "sed -i '/^vmware_host_ip/d' /etc/cinder/cinder.conf",
                    "sed -i '/^vmware_volume_folder/d' /etc/cinder/cinder.conf",
                    "sed -i '/^vmware_host_version/d' /etc/cinder/cinder.conf",
                    cinder_cfg_cmd,
                    "systemctl restart openstack-cinder-volume",
                    
                    "sed -i '/^host_password/d' /etc/nova/nova.conf",
                    "sed -i '/^host_username/d' /etc/nova/nova.conf",
                    "sed -i '/^host_ip/d' /etc/nova/nova.conf",
                    "sed -i '/^cluster_name/d' /etc/nova/nova.conf",
                    "sed -i '/^compute_driver/d' /etc/nova/nova.conf",
                    "sed -i '/^\[DEFAULT\]$/a compute_driver = vmwareapi.VMwareVCDriver' /etc/nova/nova.conf",
                    vcenter_cfg_cmd,
                    "systemctl restart openstack-ceilometer-compute",
                    "(systemctl restart openstack-nova-compute && echo 'compute service success') \
                    || echo 'compute service failed'",
               
                      ]
        
        """如果配置驱动失败，则恢复默认的配置"""
        reset_cmd_list = [
                        "systemctl stop openstack-cinder-volume",
                        "systemctl stop openstack-nova-compute",
                        "systemctl stop openstack-ceilometer-compute.service",
                        "sed -i '/^hypervisor_inspector/d' /etc/ceilometer/ceilometer.conf",
                        "systemctl start openstack-ceilometer-compute.service",
                        "sed -i '/^volume_driver/d' /etc/nova/nova.conf",
                        "sed -i '/^compute_driver/d' /etc/nova/nova.conf",
                        "sed -i '/^\[DEFAULT\]$/a compute_driver = libvirt.LibvirtDriver' /etc/nova/nova.conf",
                        "systemctl restart openstack-ceilometer-compute",
                        "systemctl start openstack-nova-compute",
                          ]
        
        self._add_platform_instance(instance_info, cmd_list, reset_cmd_list)
      
        
    def remove_vcenter_platform_instance(self, instance_info):
        """
        删除vcenter平台实例
        _@instance_info:平台实例的基础信息,集群的用户名，密码和地址信息，接管集群等
        """
        cmd_list = [
                        "systemctl stop openstack-cinder-volume",
                        "systemctl stop openstack-nova-compute",
                        "systemctl stop openstack-ceilometer-compute.service",
                        "sed -i '/^hypervisor_inspector/d' /etc/ceilometer/ceilometer.conf",
                        "systemctl start openstack-ceilometer-compute.service",
                        "sed -i '/^volume_driver/d' /etc/nova/nova.conf",
                        "sed -i '/^compute_driver/d' /etc/nova/nova.conf",
                        "sed -i '/^\[DEFAULT\]$/a compute_driver = libvirt.LibvirtDriver' /etc/nova/nova.conf",
                        "(systemctl start openstack-nova-compute && echo 'compute service success') \
                        || echo 'compute service failed'"
                          ]
        
        self._remove_platform_instance(instance_info, cmd_list)
        
            
    def edit_vcenter_instance(self, instance_info):
        pass
    
    def sync_vcenter_instance(self, instance_info):
        """
        同步vcenter平台的实例
        同步的内容包括：
        a. 同步虚拟机的名称，状态，电源状态 
        b. 同步在vcenter上创建的虚拟机到本的记录
        c. 删除在vcenter上已经删除的虚拟机在本地的记录
        """
        self.update_platform_dc_cluster()
        self._synchronism(instance_info)
    
    def get_vcenter_uuid_maps_info(self):
        """获取openstack与vcenter的虚拟机映射信息"""
        vcenter_uuid_maps = {}
        vcenter_db = PlatformDatabase(VCenterDBConfig)
        sql = "select * from vcenter_uuid_maps;"
        vcenter_db.query(sql)
        vms_info = vcenter_db.fetchAllRows()
        vcenter_db.close()
        for vm in vms_info:
            item_info = {}
            item_info["ip"] = vm[3]
            item_info["flavor_id"] = vm[4]
            vcenter_uuid_maps[vm[1]] = item_info
            
        return vcenter_uuid_maps
