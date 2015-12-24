#coding:utf-8

from platforms.platform import PlatformInstanceInfo
from utils import com_utils
from db.mysql import PlatformDatabase
from db.common import CServerDBConfig
from datetime import datetime

class CServerPlatformInstanceInfo(PlatformInstanceInfo):
    virt_type = 'cserver'
    """
    vcenter管理平台的实例信息
    """
    def __init__(self, name, domain_name, hostname, virtualplatformtype, \
                 uuid, session, virtualplatformIP, virtualplatformusername, \
                 virtualplatformpassword, dc_cluster=None):
        PlatformInstanceInfo.__init__(self, name, domain_name, hostname, \
                                      virtualplatformtype, uuid, session, \
                                      virtualplatformIP, virtualplatformusername, \
                                      virtualplatformpassword, dc_cluster)

    def get_platform_base_info(self):
        baseinfo = {}
        for dc in self._session.get_datacenter_list():
            cluster_list = self._session.get_dc_cluster(dc['id'])
            baseinfo[dc['name']] = []
            for cluster in cluster_list:
                baseinfo[dc['name']].append(cluster['name'])
                
#         print baseinfo
        return baseinfo
    
    def get_cluster_cpu_memory(self, cluster_id):
        """获取vcenter平台中集群的cpu和内存信息"""
        cluster_cpu_num = 0
        cluster_memory_size = 0
        for host in self._session.get_cluster_host(cluster_id):
            status, host_cpu_num, host_memory = self._session.get_host_status_cpu_memory_info(host['id'])
            cluster_cpu_num += host_cpu_num
            cluster_memory_size += host_memory
            
        return (cluster_cpu_num, cluster_memory_size)
    

    def get_sll_dc_cpu_memeory(self):
        """获取cserver平台中接管的所有数据中心的cpu和内存信息"""
        dc_cpu_num = 0
        dc_memory_size = 0
        for datacenter in self._session.get_datacenter_list():
            if datacenter["name"] in self._dc_cluster.keys():
                for cluster in self._session.get_dc_cluster(datacenter['id']):
                    if cluster["name"] in self._dc_cluster[datacenter["name"]]:
                        cpu_memory_info = self.get_cluster_cpu_memory(cluster['id'])
                        dc_cpu_num += cpu_memory_info[0]
                        dc_memory_size += cpu_memory_info[1]
        return dc_cpu_num, com_utils.convert_kb_to_g(dc_memory_size)
    
    
    def get_dc_cpu_memeory(self, dc_name):
        """获取cserver平台中指定数据中心的cpu和内存信息"""
        dc_cpu_num = 0
        dc_memory_size = 0
        for datacenter in self._session.get_datacenter_list():
            if datacenter["name"] == dc_name and datacenter["name"] in self._dc_cluster.keys():
                for cluster in self._session.get_dc_cluster(datacenter['id']):
                    if cluster["name"] in self._dc_cluster[datacenter["name"]]:
                        cpu_memory_info = self.get_cluster_cpu_memory(cluster['id'])
                        dc_cpu_num += cpu_memory_info[0]
                        dc_memory_size += cpu_memory_info[1]
                break

        return dc_cpu_num, com_utils.convert_kb_to_g(dc_memory_size)
    
    def get_dc_datastore(self):
        """获取cserver平台中数据中心的存储信息"""
        dc_ds_info = {}
        for dc in self._session.get_datacenter_list():
            dc_ds_info[dc["name"]] = self._session.get_dc_datastore(dc["id"])
        print "dc_ds_info:", dc_ds_info
        return dc_ds_info
    
    def get_dc_info(self):
        """获取cserver平台中数据中心的详细信息"""
        dc_info_list = []
        if not self._dc_cluster:
            return []
        
        dc_ds_info = self.get_dc_datastore()
        
        for dc in self._dc_cluster.keys():
            used  = dc_ds_info[dc][0] if dc_ds_info else 0
            freeSpace = dc_ds_info[dc][1] if dc_ds_info else 0
            capacity  = dc_ds_info[dc][2] if dc_ds_info else 0
            cpu_num, memory_size = self.get_dc_cpu_memeory(dc)
            dc_info_list.append({"name": dc, "mcenter": self._name, \
                                 "cpu": cpu_num, "memory": memory_size, \
                                 "free": freeSpace, "used": used, \
                                 "capacity": capacity, \
                                 "domain": self._domain_name, \
                                              })
        print "dc_info_list:", dc_info_list
        return dc_info_list
    
    def get_dc_cluster_info(self):
        """获取cserver平台中集群的详细信息"""
        cluster_info_list = []
        if not self._dc_cluster:
            return []
        
        for datacenter in self._session.get_datacenter_list():
            for datacenter["name"] in self._dc_cluster.keys():
                for cluster in self._session.get_dc_cluster(datacenter['id']):
                    if cluster["name"] in self._dc_cluster[datacenter["name"]]:
                        cpu_num, memory_size = self.get_cluster_cpu_memory(cluster["id"])
                        memory = com_utils.convert_kb_to_g(memory_size)
                        cluster_info_list.append({"name": cluster["name"], "datacenter": datacenter["name"], 
                                                  "virtualplatformtype": self.virt_type, \
                                                  "domain": self._domain_name, "id": cluster["id"], \
                                                  "cpu": cpu_num, "memory": memory, \
                                                  "free": "0", "used": "0", "total": "0"})
        return cluster_info_list
        
    def get_dc_cluster_host_info(self, is_monitor=False):
        """获取cserver平台中主机的详细信息"""
        host_info_list = []
        if not self._dc_cluster:
            return []
        
        for datacenter in self._session.get_datacenter_list():
            if datacenter["name"] in self._dc_cluster.keys():
                for cluster in self._session.get_dc_cluster(datacenter['id']):
                    if cluster["name"] in self._dc_cluster[datacenter["name"]]:
                        for host in self._session.get_cluster_host(cluster["id"]):
                            host_status, host_cpu_num, memory_size = self._session.get_host_status_cpu_memory_info(host["id"])
                            host_memory = com_utils.convert_kb_to_g(memory_size)
                            network_receive_rate = network_transmit_rate = 0
                            network_usage = host_cpu_usage = host_memory_usage = network_flow = 0
                            timestamp = ""
                            address = self._session.get_host_address(host["id"])
                            if is_monitor:
                                network_receive_rate, network_transmit_rate = self._session.get_host_network_rate(host["id"])
                                network_usage = self._session.get_host_network_usage(host["id"])
                                host_cpu_usage, host_memory_usage = self._session.get_host_cpu_memory_usage(host["id"])
                                network_flow = network_receive_rate + network_transmit_rate
                                timestamp = datetime.today()
                            host_info_list.append({"name": host["name"], "datacenter": datacenter["name"], "timestamp": timestamp, \
                                                   "domain": self._domain_name, "cluster": cluster["name"], \
                                                   'network_receive_rate': network_receive_rate, \
                                                   "network_transmit_rate": network_transmit_rate, \
                                                   "network_flow": network_flow, \
                                                   "status": host_status, "cpu": host_cpu_num, "network_usage": network_usage, "address": address, \
                                                   "memory": host_memory, "memory_usage": host_memory_usage, "cpu_usage": host_cpu_usage})
#         print "host_info_list:", host_info_list

        return host_info_list
    
    def get_template_list(self):
        return self._session.get_template_list()
    
    def get_vms_info(self, is_monitor=False):
        """获取cserver平台中虚拟机的详细信息"""
        vms_info_list = []
        cluster_id_list = []
        
        vms_list = self._session.get_vms_list(is_monitor)
        
        for datacenter in self._session.get_datacenter_list():
            if datacenter["name"] in self._dc_cluster.keys():
                for cluster in self._session.get_dc_cluster(datacenter['id']):
                    cluster_id_list.append(cluster['id'])
                    
        cserver_uuid_maps = self.get_cserver_uuid_maps_info()
        for vm in vms_list:
            if vm["cluster_id"] in cluster_id_list:
                if vm["id"] in cserver_uuid_maps:
                    vm["openstack_uuid"] = cserver_uuid_maps[vm["id"]]["openstack_uuid"]
                vms_info_list.append(vm)
#         print "vms_info_list:", vms_info_list
        return vms_info_list
    
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
            item_info["openstack_uuid"] = vm[1]
#             item_info["cserver_uuid"] = vm[2]
            item_info["ip"] = vm[3]
            item_info["flavor_id"] = vm[4]
            cserver_uuid_maps[vm[2]] = item_info
            
        return cserver_uuid_maps

        
        
    