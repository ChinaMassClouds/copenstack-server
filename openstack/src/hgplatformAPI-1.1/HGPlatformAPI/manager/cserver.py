#coding:utf-8

from db.mysql import NovaDatabase
from db.common import NovaDBConfig
from base import PlatformManager
from exception import RequestError, LoginCServerFailed
from platforms.cserver.session import CServerAPISession
from platforms.cserver.cserverplatform import CServerPlatformInstanceInfo
import uuid
from db.mysql import PlatformDatabase
from db.common import CServerDBConfig
from pymongo import Connection
from pymongo.errors import ConnectionFailure
from utils import com_utils
from logrecord import log

class CSeverPlatformManager(PlatformManager):
    _ptype = "cserver"
    def __init__(self):
        self._CSever_list = []
        super(CSeverPlatformManager, self).__init__()
    
    def create_platform_info_obj(self, instance_info):
        """
        创建平台信息对象
        _@instance_info: 平台的地址，用户名和密码等信息
        """
        try:
            session = CServerAPISession(instance_info["virtualplatformIP"], \
                                           instance_info["virtualplatformusername"], \
                                           instance_info["virtualplatformpassword"])
        except RequestError:
            raise LoginCServerFailed
        
         
        uuidv = instance_info.get("uuid", None)
        dc_cluster = instance_info.get("datacentersandclusters", None)
        print "instance_info:", instance_info
        cs_instance = CServerPlatformInstanceInfo(instance_info["name"], \
                                                  instance_info["domain_name"], \
                                                  instance_info["hostname"], \
                                                  instance_info["virtualplatformtype"], \
                                                  uuidv, session, \
                                                  instance_info["virtualplatformIP"], \
                                                  instance_info["virtualplatformusername"], \
                                                  instance_info["virtualplatformpassword"], \
                                                  dc_cluster)
        return cs_instance
        
    
    def add_CSever_platform_instance(self, platform_info):
        """
        添加cserver平台实例
        _@platform_info:平台实例的基础信息,集群的用户名，密码和地址信息，接管集群等
        """
        cluster_list = []
        cluster_str = ""
        username = platform_info["virtualplatformusername"]
        password = platform_info["virtualplatformpassword"]
        ip = platform_info["virtualplatformIP"]
        
        dc_cluster = platform_info["datacentersandclusters"]
        for dc in dc_cluster:
            for cluster in dc_cluster[dc]:
                cluster_list.append(cluster)
        
        for cluster in cluster_list:
            cluster_str += "cserver_cluster_name = %s\\n" % cluster
            
        vcenter_cfg_cmd = "sed -i \"/^\[ovirt\]$/a cserver_host_password = %s \\ncserver_host_username = %s\\ncserver_host_ip = %s\\n%s\" /etc/nova/nova.conf " \
                     % (password, username, ip, cluster_str)
                     
        """配置/etc/nova/nova.conf中的计算服务的驱动为cserver类型"""
        cmd_list = [
                    "grep '\[ovirt\]' /etc/nova/nova.conf || echo '[ovirt]' >> /etc/nova/nova.conf",
                    "sed -i '/^cserver_host_password/d' /etc/nova/nova.conf",
                    "sed -i '/^cserver_host_username/d' /etc/nova/nova.conf",
                    "sed -i '/^cserver_host_ip/d' /etc/nova/nova.conf",
                    "sed -i '/^cserver_cluster_name/d' /etc/nova/nova.conf",
                    "sed -i '/^compute_driver/d' /etc/nova/nova.conf",
                    "sed -i '/^\[DEFAULT\]$/a compute_driver = ovirt.OvirtDriver' /etc/nova/nova.conf",
                    vcenter_cfg_cmd,
                    "(systemctl restart openstack-nova-compute && echo 'compute service success') \
#                       || echo 'compute service failed'",
               
                      ]
        """如果配置驱动失败，则恢复默认的配置"""
        reset_cmd_list = [
                        "systemctl stop openstack-nova-compute",
                        "sed -i '/^compute_driver/d' /etc/nova/nova.conf",
                        "sed -i '/^\[DEFAULT\]$/a compute_driver = libvirt.LibvirtDriver' /etc/nova/nova.conf",
                        "systemctl restart openstack-nova-compute",
                          ]
        
        
        self._add_platform_instance(platform_info, cmd_list, reset_cmd_list)
      

    def remove_csever_platform_instance(self, platform_info):
        """
        删除cserver平台实例
        _@platform_info:平台实例的基础信息,集群的用户名，密码和地址信息，接管集群等
        """
        cmd_list = [
                        "systemctl stop openstack-nova-compute",
                        "sed -i '/^compute_driver/d' /etc/nova/nova.conf",
                        "sed -i '/^\[DEFAULT\]$/a compute_driver = libvirt.LibvirtDriver' /etc/nova/nova.conf",
                        "(systemctl start openstack-nova-compute && echo 'compute service success') \
                        || echo 'compute service failed'",
                          ]
        
        self._remove_platform_instance(platform_info, cmd_list)
        
        
    def sync_cserver_instance(self, platform_info):
        """
        同步cserver平台的实例
        同步的内容包括：
        a. 同步虚拟机的名称，状态，电源状态 
        b. 同步在cserver上创建的虚拟机到本的记录
        c. 删除在cserver上已经删除的虚拟机在本地的记录
        """
        self.update_platform_dc_cluster()
        self._synchronism(platform_info)
        

    def get_specity_platform_cluster_info_list(self, platform_info):
        """
        根据平台的名称获取该平台的下接管的集群信息
        """
        for csobj in self._get_platform_info_obj_list():
            if csobj.name == platform_info["name"]:
                    return csobj.get_dc_cluster_info()
                        
        return []
        
            
    def get_cserver_uuid_maps_info(self):
        """获取openstack与cserver的虚拟机映射信息"""
        cserver_uuid_maps = {}
        cserver_db = PlatformDatabase(CServerDBConfig)
        sql = "select * from cserver_uuid_maps;"
        cserver_db.query(sql)
        vms_info = cserver_db.fetchAllRows()
        cserver_db.close()
        for vm in vms_info:
            item_info = {}
            item_info["ip"] = vm[3]
            item_info["flavor_id"] = vm[4]
            cserver_uuid_maps[vm[1]] = item_info
            
        return cserver_uuid_maps


    def get_record_wrapper_base_info(self):
        user_id = com_utils.get_user_id("sysadmin")
        project_id = com_utils.get_tenant_id("admin")
        base_wrapper_info = {
                     "user_id" : user_id,
                     "resource_metadata": {},
                     "project_id": project_id,
                     "counter_type": "gauge"
                             }
        
        return base_wrapper_info
        
    def get_record_vm_wrapper_info(self, vm_info):
        vm_wrapper_info_list = []
        base_wrapper_info = self.get_record_wrapper_base_info()
        
        vm_unit_map = {
                    "cpu_usage": {
                                     "counter_name": "cpu_util",
                                     "counter_unit": "%",
                                     },
                    "memory_usage": {
                                     "counter_name": "memory.usage",
                                     "counter_unit": "%",
                                     },
                    "disk_usage": {
                                     "counter_name": "disk.usage",
                                     "counter_unit": "%",
                                     },
                    "disk_read_rate": {
                                     "counter_name": "disk.read.bytes.rate",
                                     "counter_unit": "B/s",
                                     },
                    "disk_write_rate": {
                                     "counter_name": "disk.write.bytes.rate",
                                     "counter_unit": "B/s",
                                     },
                    "network_transmit_rate": {
                                     "counter_name": "network.outgoing.bytes.rate",
                                     "counter_unit": "B/s",
                                     },
                    "network_receive_rate": {
                                     "counter_name": "network.incoming.bytes.rate",
                                     "counter_unit": "B/s",
                                     },
                    "network_flow": {
                                     "counter_name": "network.bytes",
                                     "counter_unit": "B/s",
                                     },
                    }
        
        
        for monitor_key in vm_info:
            if monitor_key in vm_unit_map:
                wrapper_info = {
                    "counter_name": vm_unit_map[monitor_key]["counter_name"],
                    "timestamp": vm_info["timestamp"],
                    "resource_id": vm_info["openstack_uuid"],  #hardware host IP, vm vm_id
                    "source" : "cserver", #hardware: hardware, vm    : openstack, cserver
                    "counter_unit" : vm_unit_map[monitor_key]["counter_unit"],
                    "counter_volume": vm_info[monitor_key],
                    "message_id": str(uuid.uuid4()),
                    "message_signature": str(uuid.uuid4()),
                    "recorded_at": vm_info["timestamp"],
                    }
                wrapper_info.update(base_wrapper_info)
                vm_wrapper_info_list.append(wrapper_info)
            
        return vm_wrapper_info_list
                
    def get_record_host_wrapper_info(self, host_info):
        host_wrapper_info_list = []
        base_wrapper_info = self.get_record_wrapper_base_info()
        
        host_unit_map = {
                    "cpu_usage": {
                                     "counter_name": "hardware.cpu.load.1min",
                                     "counter_unit": "%",
                                     },
                    "memory_usage": {
                                     "counter_name": "hardware.memory.used",
                                     "counter_unit": "%",
                                     },
                    "network_transmit_rate": {
                                     "counter_name": "hardware.network.outcoming.bytes",
                                     "counter_unit": "B/s",
                                     },
                    "network_receive_rate": {
                                     "counter_name": "hardware.network.incoming.bytes",
                                     "counter_unit": "B/s",
                                     },
                    "network_flow": {
                                     "counter_name": "hardware.network.bytes",
                                     "counter_unit": "B/s",
                                     },
                    }
        
        for monitor_key in host_info:
            if monitor_key in host_unit_map:
                wrapper_info = {
                    "counter_name": host_unit_map[monitor_key]["counter_name"],
                    "timestamp": host_info["timestamp"],
                    "resource_id": host_info["address"],  #hardware host IP, vm vm_id
                    "source" : "hardware", #hardware: hardware, vm    : openstack, cserver
                    "counter_unit" : host_unit_map[monitor_key]["counter_unit"],
                    "counter_volume": host_info[monitor_key],
                    "message_id": str(uuid.uuid4()),
                    "message_signature": str(uuid.uuid4()),
                    "recorded_at": host_info["timestamp"],
                    }
                wrapper_info.update(base_wrapper_info)
                host_wrapper_info_list.append(wrapper_info)
            
        return host_wrapper_info_list

    def get_cserver_monitor_info(self):
        wrapper_list_info = []
        for csobj in self._get_platform_info_obj_list():
            vm_list_info = csobj.get_vms_info(is_monitor=True)
            host_list_info = csobj.get_dc_cluster_host_info(is_monitor=True)
            for vm_info in vm_list_info:
                vm_wrapper_list_info = self.get_record_vm_wrapper_info(vm_info)
                wrapper_list_info.extend(vm_wrapper_list_info)
                
            for host_info in host_list_info:
                host_wrapper_list_info = self.get_record_host_wrapper_info(host_info)
                wrapper_list_info.extend(host_wrapper_list_info)
                
        return wrapper_list_info
                
    def record_cserver_monitor_info(self):
        try:
            mongodb_ip = com_utils.get_mongodb_ip()
            ceilometerdb = "ceilometer"
            c = Connection(host = mongodb_ip, port=27017)
        except ConnectionFailure, e:
            log.logger.info("Could not connect to MongoDB: %s" % e)
            return
        dbh = c[ceilometerdb]
        assert dbh.connection == c
        
        for monitor_info in self.get_cserver_monitor_info():
            dbh.meter.insert(monitor_info, safe=True)
#             print "Successfully inserted document: %s" % monitor_info
            log.logger.info("Successfully inserted monitor info: %s" % monitor_info)
                
            
