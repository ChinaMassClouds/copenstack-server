#coding:utf-8

# from platforms.vcenter.session import VMwareAPISession
from platforms.vcenter import vmwareop
from platforms.platform import PlatformInstanceInfo
from utils import com_utils
# from requests.models import json_dumps

class VCenterPlatformInstanceInfo(PlatformInstanceInfo):
    virt_type = 'vcenter'
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
        
            
    def get_datacenter_num(self):
        """获取vcenter平台中数据中心的数量"""
        return len(self.get_datacenter_list)
    
    def get_datacenter_list(self):
        """获取vcenter平台中数据中心名称列表"""
        datacenter_list = []
        for dc in vmwareop.list_datacenter(self._session):
            datacenter_list.append(dc[0])
        return datacenter_list
    
    def get_platform_base_info(self):
        """获取vcenter平台中数据中心和集群基础信息"""
        baseinfo = {}
        for dc in vmwareop.list_datacenter(self._session):
            cluster_list = vmwareop.get_dc_cluster(self._session, dc[1])
            baseinfo[str(dc[0])] = []
            for cluster in cluster_list:
                baseinfo[str(dc[0])].append(cluster[0])
        return baseinfo
    
    def get_dc_datastore(self):
        """获取vcenter平台中数据中心的存储信息"""
        dc_ds_info = {}
        for dc in vmwareop.list_datacenter(self._session):
            datacenter_name = str(dc[0])
            dc_ref = dc[1]
            totalCapacity = 0
            freeCapacity = 0
            used = 0
            if datacenter_name in self._dc_cluster.keys():
                (totalCapacity,freeCapacity) = vmwareop.get_object_datastore(self._session, dc_ref, 'Datacenter')
                used = totalCapacity - freeCapacity
                dc_ds_info[datacenter_name] = [com_utils.convert_kb_to_g(used), \
                                               com_utils.convert_kb_to_g(freeCapacity), \
                                               com_utils.convert_kb_to_g(totalCapacity)]
        return dc_ds_info
    
    
    def get_dc_info(self):
        """获取vcenter平台中数据中心的详细信息"""
        dc_info_list = []
        
        dc_ds_info = self.get_dc_datastore()
        for dc in self._dc_cluster.keys():
            used  = dc_ds_info[dc][0] if dc_ds_info else 0
            freeSpace = dc_ds_info[dc][1] if dc_ds_info else 0
            capacity  = dc_ds_info[dc][2] if dc_ds_info else 0
            cpu_num, memory_size = self.get_dc_cpu_memeory()
            memory = com_utils.convert_kb_to_g(memory_size)
            dc_info_list.append({"name": dc, "mcenter": self._name, \
                                 "cpu": cpu_num, "memory": memory, \
                                 "free": freeSpace, "used": used, \
                                 "capacity": capacity, \
                                 "domain": self._domain_name, \
                                              })
#         print "dc_info_list:", dc_info_list

        return dc_info_list
    
    def get_dc_cluster_info(self):
        """获取vcenter平台中集群的详细信息"""
        cluster_info_list = []
        
        for datacenter in self._dc_cluster.keys():
            for cluster in self._dc_cluster[datacenter]:
                for clusterref in vmwareop.get_cluster_ref(self._session, cluster):
                    (totalCapacity,freeCapacity) = vmwareop.get_object_datastore(self._session, clusterref, 'ClusterComputeResource')
                    used = com_utils.convert_kb_to_g(totalCapacity - freeCapacity)
                    free = com_utils.convert_kb_to_g(freeCapacity)
                    total = com_utils.convert_kb_to_g(totalCapacity)
                    cpu_num, memory_size = self.get_cluster_cpu_memory(clusterref)
                    memory = com_utils.convert_kb_to_g(memory_size)
#                     print "memory_size:", memory_size, cpu_num
                    cluster_info_list.append({"name": cluster, "datacenter": datacenter, 
                                              "virtualplatformtype": self.virt_type, \
                                              "domain": self._domain_name, \
                                              "cpu": cpu_num, "memory": memory, \
                                              "free": free, "used": used, "total": total})
#         print "cluster_info_list:", cluster_info_list
        return cluster_info_list
    
    def get_dc_cluster_host_info(self):
        """获取vcenter平台中主机的详细信息"""
        host_info_list = []
        
        for datacenter in self._dc_cluster.keys():
            for cluster in self._dc_cluster[datacenter]:
                for clusterref in vmwareop.get_cluster_ref(self._session, cluster):
                    for host in vmwareop.get_cluster_host(self._session, clusterref):
                        hostip = ""
                        if host[0]:
                            hostip = host[0][0]
                        hostname = host[1]
                        hostref = host[2]
                        host_status = vmwareop.get_host_status(self._session, hostref)
                        host_cpu_num, host_cpu_hz = vmwareop.get_host_cpu_info(self._session, hostref)
                        host_memory = com_utils.convert_kb_to_g(vmwareop.get_host_memSize(self._session, hostref))
                        host_info_list.append({"name": hostname, "datacenter": datacenter, \
                                               "domain": self._domain_name, \
                                               "address": hostip, "cluster": cluster, \
                                               "status": host_status, "cpu": host_cpu_num,\
                                               "memory": host_memory})

        return host_info_list
    
    def get_vms_info(self):
        """获取vcenter平台中虚拟机的详细信息"""
        vms_info_list = []
        for datacenter in self._dc_cluster.keys():
            for cluster in self._dc_cluster[datacenter]:
                for clusterref in vmwareop.get_cluster_ref(self._session, cluster):
                    for host in vmwareop.get_cluster_host(self._session, clusterref):
                        vm_info = vmwareop.get_vm_info_list(self._session, host[2])
                        vms_info_list.extend(vm_info)
                        
        return vms_info_list
    
    def get_cluster_cpu_memory(self, clusterref):
        """获取vcenter平台中集群的cpu和内存信息"""
        cluster_cpu_num = 0
        cluster_memory_size = 0
        for host in vmwareop.get_cluster_host(self._session, clusterref):
            hostref = host[2]
            host_cpu_num, host_cpu_hz = vmwareop.get_host_cpu_info(self._session, hostref)
            host_memory = vmwareop.get_host_memSize(self._session, hostref)
            cluster_cpu_num += host_cpu_num
            cluster_memory_size += host_memory
            
        return (cluster_cpu_num, cluster_memory_size)
    
    def get_dc_cpu_memeory(self):
        """获取vcenter平台中数据中心的cpu和内存信息"""
        dc_cpu_num = 0
        dc_memory_size = 0
        for datacenter in self._dc_cluster.keys():
            for cluster in self._dc_cluster[datacenter]:
                for clusterref in vmwareop.get_cluster_ref(self._session, cluster):
                    cpu_memory_info = self.get_cluster_cpu_memory(clusterref)
                    dc_cpu_num += cpu_memory_info[0]
                    dc_memory_size += cpu_memory_info[1]
        return dc_cpu_num, dc_memory_size
                        
