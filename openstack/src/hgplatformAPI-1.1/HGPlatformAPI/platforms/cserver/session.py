# -*- coding: utf-8 -*-

import requests
import json
import base64
from exception import RequestError, CServerConnectionError, \
                      CServerRequestError
from platforms import common
from utils import com_utils
from logrecord import log
from datetime import datetime

class HttpRequests(object):
    _instance = 0
    def __init__(self, host, username, password, port, domain):
        super(HttpRequests,self).__init__()
        self._host = host
        self._port = port
        self._domain = domain
        cert = "Basic " + base64.b64encode('%s@%s:%s' %(username,domain,password))
        self._headers = {
                        'Host': 'identity.api.openstack.org',
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'Accept-Encoding': 'gzip, deflate',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Cookie': 'username=root; kimchiLang=zh_CN',
                        'Authorization': cert,
                        'X-Requested-With': 'XMLHttpRequest',
                                }
        
    
    def getServiceURL(self, url):
        return "https://" + self._host + ":" + str(self._port) + url


    def getRequestInfo(self, url):
        """
        获取请求的信息
        @url 请求的url信息
        """
        try:
            request = requests.get(self.getServiceURL(url), headers=self._headers, verify=False)
            if request.ok:
                return request.json()
            else:
                log.logger.error("RequestError" + url + " " + request.content)
                raise RequestError(url + " " + request.content)
        
        except requests.exceptions.ConnectionError, e:
            raise CServerConnectionError()
        


class CServerAPISession(object):
    
    def __init__(self, host, server_username, server_password, domain="internal", port=443):
        self._host = host
        self._server_username = server_username
        self._server_password = server_password
        self._port = port 
        self._domain = domain
        self._create_session()
        
    def get_host_port(self):
        return "%s:%s" % (self._host, str(self._port))
    
    def _create_session(self):
        self._request = HttpRequests(self._host, self._server_username, self._server_password, \
                                     self._port, self._domain)
        self.get_datacenter_list()
        
        
    def get_datacenter_list(self):
        '''
        获得数据中心列表
        :return 字典{name:数据中心名称,id：uuid}
        '''
        dc_list = []
        dc_info = self._request.getRequestInfo(common.CSERVER_DATACENTERS_LIST_URL)
        if dc_info and dc_info.has_key("data_center"):
            for dict_dc in dc_info['data_center']:
                dc= {}
                dc['name'] = dict_dc['name']
                dc['id'] = dict_dc['id']
                dc_list.append(dc) 
#         print dc_list
        return dc_list
    
        
    def get_dc_cluster(self, dc_id):
        '''
        获得数据中心下的集群列表
        
        :param dc :数据中心的字典对象
        :return 字典{name:集群名称,id：uuid}
        '''
        cluster_list = []
        cluster_info = self._request.getRequestInfo(common.CSERVER_DC_CLUSTER_LIST_URL % dc_id)
        if cluster_info and cluster_info.has_key("cluster"):
            for dict_dc in cluster_info['cluster']:
                dc= {}
                dc['name'] = dict_dc['name']
                dc['id'] = dict_dc['id']
                cluster_list.append(dc) 
#         print "cluster_list:", cluster_list
        return cluster_list


    def get_object_properties(self, dict_objects,properties):
        '''
        获取字典对象中指定属性的值
        
        :param dict_objects :从服务端获取的字典对象
        :param properties :要获得的属性集合
        :return {propert:value}的字典
        '''
        
        dict_result ={}
        for prop in properties:
                dict_result[prop] = dict_objects[prop]    
        
        return dict_result
    
    
    def get_cluster_host(self, cluster_id):
        '''
        获得集群下的主机列表
        
        :param cluster_id :集群的id
        :return 字典{name:主机名称,id：uuid}
        '''
        host_list = []
        
        host_info = self._request.getRequestInfo(common.CSERVER_HOST_LIST_URL)
        if host_info and host_info.has_key("host"):
            for host in host_info["host"]:
                if host["cluster"]['id'] == cluster_id:
                    host_list.append(self.get_object_properties(host, ['name','id']))
                
        return host_list
   
        
    def get_host_status_cpu_memory_info(self, host_id):
        '''
        获得主机的状态，cpu,内存等信息
        
        :param host_id :主机的id
        :return 主机的状态，cpu, 内存
        '''
        cpu_size = 0
        memeory_size = "0"
        status = "unknown"
        host_info = self._request.getRequestInfo(common.CSERVER_HOST_URL % host_id)
        if host_info and host_info.has_key("cpu"):
            if 'topology' in host_info['cpu'].keys():
                cores = int(host_info['cpu']['topology']["cores"])
                threads = int(host_info['cpu']['topology']["threads"])
                cpu_size = cores * threads
            if 'memory' in host_info.keys():
                memeory_size = host_info["memory"]
            if 'status' in host_info.keys():
                status = host_info["status"]["state"]
#         print cpu_size, memeory_size
        return status, cpu_size, memeory_size
    
    def get_host_total_cpu(self, host_id):
        '''
        获得主机总的cpu
        
        :param host_id :主机的id
        :return cpu, 内存
        '''
        cpu_speed = 0
        host_info = self._request.getRequestInfo(common.CSERVER_HOST_URL % host_id)
        if host_info and host_info.has_key("cpu"):
            if 'speed' in host_info['cpu'].keys():
                cpu_speed = host_info['cpu']["speed"]
              
#         print "cpu_speed:", cpu_speed
        return cpu_speed
        
    def get_host_address(self, host_id):
        address = ""
        host_info = self._request.getRequestInfo(common.CSERVER_HOST_URL % host_id)
        if host_info and host_info.has_key("address"):
            address = host_info["address"]
            
        return address
        
    def get_host_idle_cpu(self, host_id):
        '''
        获取主机剩余的cpu的资源量
        
        :param host的id
        :return 剩余的资源总量
        '''
        idle = 0
        host_static_info = self._request.getRequestInfo(common.CSERVER_HOST_STATISTICS_URL % host_id)
        if host_static_info and host_static_info.has_key("statistic"):
            for info in host_static_info["statistic"]:
                if info.has_key("name") and info['name'] =='cpu.current.idle':
                    val_list = info['values']['value']
                    for val in val_list:
                        if 'datum' in val.keys():
                            idle = val['datum']    
        return idle

        
        
    def get_dc_datastore(self, dc_id):
        '''
        获取数据中心下的存储容量
        :param dc_id :数据中心的id
        :return 元组(储存总量,已使用量)
        '''
        totalCapacity = 0
        freeCapacity = 0
        used = 0
        storages_info = self._request.getRequestInfo(common.CSERVER_DC_STORAGE_URL % dc_id)
        if storages_info and storages_info.has_key("storage_domain"):
            storages = storages_info["storage_domain"]
            if storages and len(storages)>0:
                for storage in storages:
                    totalCapacity += storage["available"] + storage["used"]
                    freeCapacity += storage["available"]
                    used += storage["used"]
                    
        totalCapacity= com_utils.convert_kb_to_g(totalCapacity)
        freeCapacity= com_utils.convert_kb_to_g(freeCapacity)
        used= com_utils.convert_kb_to_g(used)
        
#         print (totalCapacity,freeCapacity, used) 
        return (used, freeCapacity, totalCapacity)


    def get_vm_nic_list(self, vm_id):
        vm_nic_list = []
#         url = '/massclouds-svmanager/api/vms/' + vm_id + '/nics'
        
        req_content = self._request.getRequestInfo(common.CSERVER_VM_NIC_LIST_URL % vm_id)
        if req_content and req_content.has_key('nic'):
            raw_vm_list_nic = req_content['nic']
            for vm_nic in raw_vm_list_nic:
                vm_nic_list.append(self.get_object_properties(vm_nic, ['id','name','active']))
        return vm_nic_list

    def get_host_nic_list(self, host_id):
        list_nic = []
#         url = '/massclouds-svmanager/api/hosts/' + host_id + '/nics'
        raw_host_list_nic = self._request.getRequestInfo(common.CSERVER_HOST_NIC_LIST_URL % host_id)
        if raw_host_list_nic and raw_host_list_nic.has_key('host_nic'):
            raw_host_list_nic = raw_host_list_nic['host_nic']
            for host_nic in raw_host_list_nic:
                list_nic.append(self.get_object_properties(host_nic, ['id','name','status']))
        return list_nic
    
    def get_host_nic_status(self, host_id, host_nic_id): 
#         url = '/massclouds-svmanager/api/hosts/' + host_id + '/nics/' + host_nic_id
        info = self._request.getRequestInfo(common.CSERVER_HOST_NIC_URL % (host_id, host_nic_id))
        if info and info.has_key('status'):
            status = info["status"]
            if status["state"] == "up":
                return True
        return False
        
    def get_host_nic_rate(self, host_id, host_nic_id):
#         url = '/massclouds-svmanager/api/hosts/' + host_id + '/nics/' + host_nic_id
        info = self._request.getRequestInfo(common.CSERVER_HOST_NIC_URL % (host_id, host_nic_id))
        if info and info.has_key('speed'):
            return info['speed']
        
        return 0
    
    def get_host_nic_transmit_rate(self, host_id, host_nic_id):
#         url = '/massclouds-svmanager/api/hosts/'+host_id+'/nics/'+host_nic_id+ '/statistics'
        info = self._request.getRequestInfo(common.CSERVER_HOST_NIC_STATISTICS_URL % (host_id, host_nic_id))
        if info and info.has_key("statistic"):
            results = info["statistic"]
            for result in results:
                if result['name'] == 'data.current.tx':
                    values = result['values']["value"]
                    for value in  values :
                        if "datum" in value.keys():
                            return value['datum']
        return 0
    
    def get_host_nic_receive_rate(self, host_id, host_nic_id):
#         url = '/massclouds-svmanager/api/hosts/'+ host_id+'/nics/' + host_nic_id + '/statistics'
        info = self._request.getRequestInfo(common.CSERVER_HOST_NIC_STATISTICS_URL % (host_id, host_nic_id))
        if info and info.has_key("statistic"):
            results = info["statistic"]
            for result in results:
                if result['name'] == 'data.current.rx':
                    values = result['values']["value"]
                    for value in  values :
                        if "datum" in value.keys():
                            return value['datum']
        return 0
    
    
    def get_host_network_usage(self, host_id):
        """获取主机的网络使用率"""
        speed =0
        transimt = 0
        receive = 0
        network_usage = 0
        list_nic = self.get_host_nic_list(host_id)
        for nic in list_nic:
            if nic["status"]['state'] == 'up':
                speed = speed + self.get_host_nic_rate(host_id, nic["id"])
                transimt = transimt + self.get_host_nic_transmit_rate(host_id, nic["id"])
                receive = receive + self.get_host_nic_receive_rate(host_id, nic["id"])
                    
        main_value = (transimt * 8) if transimt > receive else (receive * 8)
        if speed !=0:
            network_usage = float('%.2f' % ((main_value  / (speed * 1.0)) * 100))
        return network_usage

    def get_host_network_rate(self, host_id):
        """获取主机的网络速率"""
        max_receive_rate = 0
        max_transmit_rate = 0
        list_nic = self.get_host_nic_list(host_id)
        for nic in list_nic:
            if nic["status"]['state'] == 'up':
                receive = self.get_host_nic_receive_rate(host_id, nic["id"])
                max_receive_rate = receive if receive > max_receive_rate else max_receive_rate
                transimt = self.get_host_nic_transmit_rate(host_id, nic["id"])
                max_transmit_rate = transimt if transimt > max_transmit_rate else max_transmit_rate
                
#         max_receive_rate = float('%.2f' % ((max_receive_rate * 8) / (1024 * 1024 * 1.0)))
#         max_transmit_rate = float('%.2f' % ((max_transmit_rate * 8) / (1024 * 1024 * 1.0)))
        
        return max_receive_rate, max_transmit_rate
        
    def get_vm_nic_receive_transmit_rate(self, vm_id, vm_nic_id):
        receive_rate = 0
        transmit_rate = 0
#         url = '/massclouds-svmanager/api/vms/' + vm_id + '/nics/' + vm_nic_id + '/statistics'
        info = self._request.getRequestInfo(common.CSERVER_VM_NIC_STATISTICS_URL % (vm_id, vm_nic_id))
        if info and info.has_key("statistic"):
            for result in info["statistic"]:
                if result['name'] == 'data.current.rx':
                    values = result['values']["value"]
                    for value in  values :
                        if "datum" in value.keys():
                            receive_rate = value['datum']
                elif result['name'] == 'data.current.tx':
                    values = result['values']["value"]
                    for value in  values :
                        if "datum" in value.keys():
                            transmit_rate = value['datum']
        return receive_rate, transmit_rate
    
    def get_vm_network_rate(self, vm_id):
        """获取虚拟机的网络速率"""
        max_receive_rate = 0
        max_transmit_rate = 0
        list_nic = self.get_vm_nic_list(vm_id)
        for vm_nic in list_nic:
            if vm_nic["active"] == 'true':
                receive_rate, transmit_rate = self.get_vm_nic_receive_transmit_rate(vm_id, vm_nic["id"])
                max_receive_rate = receive_rate if receive_rate > max_receive_rate else max_receive_rate
                max_transmit_rate = transmit_rate if transmit_rate > max_transmit_rate else max_transmit_rate
        
#         max_receive_rate = float('%.2f' % ((max_receive_rate * 8) / (1024 * 1024 * 1.0)))
#         max_transmit_rate = float('%.2f' % ((max_transmit_rate * 8) / (1024 * 1024 * 1.0)))
        
        return max_receive_rate, max_transmit_rate
    
    def get_vm_disk_read_write_rate(self, vm_id):
        """获取虚拟机硬盘的读写速率"""
        max_read_rate = 0
        max_write_rate = 0
        req_content = self._request.getRequestInfo(common.CSERVER_VM_DISK_URL % vm_id)
        if req_content and req_content.has_key('disk'):
            for disk in req_content["disk"]:
                static_info = self._request.getRequestInfo(common.CSERVER_VM_DISK_STATISTICS_URL % (vm_id, disk["id"]))
                if static_info and static_info.has_key("statistic"):
                    for item in static_info["statistic"]:
                        if item['name'] == 'data.current.read':
                            values = item['values']["value"]
                            for value in  values :
                                if "datum" in value.keys():
                                    read_rate = value['datum']
                                    max_read_rate = read_rate if read_rate > max_read_rate else max_read_rate
                        elif item['name'] == 'data.current.write':
                            values = item['values']["value"]
                            for value in  values :
                                if "datum" in value.keys():
                                    write_rate = value['datum']
                                    max_write_rate = write_rate if write_rate > max_write_rate else max_write_rate
                                    
#         max_read_rate = float('%.2f' % (max_read_rate / (1024 * 1024 * 1.0)))
#         max_write_rate = float('%.2f' % (max_write_rate / (1024 * 1024 * 1.0)))
        
        return max_read_rate, max_write_rate
    
    def get_vm_network_usage(self, vm_id):
        """获取虚拟机的网络速率"""
        speed =0
        transimt = 0
        receive = 0
        vm_nic_list = self.get_vm_nic_list(vm_id)
        for vm_nic in vm_nic_list:
            if vm_nic["active"] == 'true':
                pass
            
        return 0
    
    def get_host_cpu_memory_usage(self, host_id):
        """获取主机的内存使用量"""
        total_memory = 0
        actual_memory = 0
        memory_usage = 0
        cpu_five_minute_avg_load = 0
        
        req_content = self._request.getRequestInfo(common.CSERVER_HOST_STATICS_URL % host_id)
        if req_content and req_content.has_key("statistic"):
            for item in req_content["statistic"]:
                if item["name"] == "memory.total":
                    values = item['values']["value"]
                    for value in  values :
                        if "datum" in value.keys():
                            total_memory = value['datum']
                elif item["name"] == "memory.used":
                    values = item['values']["value"]
                    for value in  values :
                        if "datum" in value.keys():
                            actual_memory = value['datum']
                elif item["name"] == "cpu.load.avg.5m":
                    values = item['values']["value"]
                    for value in  values :
                        if "datum" in value.keys():
                            cpu_five_minute_avg_load = value['datum']
                
        if total_memory == 0 or actual_memory == 0:
            return cpu_five_minute_avg_load, memory_usage
        
#         print "total_memory:", total_memory, "actual_memory:", actual_memory
        memory_usage = float("%.2f" % ((actual_memory / (total_memory * 1.0)) * 100))
#         print "host memory usage:", memory_usage
        return cpu_five_minute_avg_load, memory_usage
   
   
    def get_vms_list(self, is_monitor=False):
        '''
        获取总的虚拟机列表信息
        '''
        vm_info_list = []
        req_content = self._request.getRequestInfo(common.CSERVER_VM_LIST_URL)
        if req_content and req_content.has_key('vm'):
            for vm in req_content['vm']:
                vm_info = {}
                vm_info["id"] = vm["id"]
                vm_info["openstack_uuid"] = ""
                vm_info["name"] = vm["name"]
                vm_info["hostname"] = ""
                vm_info["cluster_id"] = vm["cluster"]["id"]
                vm_info["power_state"] = vm["status"]["state"]
                vm_info["cpu"] = int(vm["cpu"]["topology"]["cores"])*int(vm["cpu"]["topology"]["threads"])
                vm_info["ram"] = int(vm["memory"]/1024.0/1024.0)
                if is_monitor:
                    vm_info["disk_usage"] = self.get_vm_disk_usage(vm["id"])
                    vm_info["network_usage"] = self.get_vm_network_usage(vm["id"])
                    vm_info["network_receive_rate"], vm_info["network_transmit_rate"] = self.get_vm_network_rate(vm["id"])
                    vm_info["disk_read_rate"], vm_info["disk_write_rate"] = self.get_vm_disk_read_write_rate(vm["id"])
                    vm_info["cpu_usage"], vm_info["memory_usage"] = self.get_vm_cpu_memory_usage(vm["id"])
                    vm_info["timestamp"] = datetime.today()
                    vm_info["network_flow"] = vm_info["network_receive_rate"] + vm_info["network_transmit_rate"]
                if "host" in vm.keys():
                    vm_info["hostname"] = self.get_vm_belong_host_name(vm["host"]["id"])
                vm_disk_size = self.get_vm_total_disk_size(vm["id"])
                vm_info["disk"] = vm_disk_size if vm_disk_size else 10.0
                vm_info["ip"] = ""
                if vm.has_key("guest_info"):
                    ip_list = vm["guest_info"]["ips"]["ip"]
                    if ip_list and ip_list[0].has_key("address"):
                        vm_info["ip"] = ip_list[0]["address"]
                        
                vm_info_list.append(vm_info)
        return vm_info_list

    def get_vm_belong_host_name(self, host_id):
        """获取虚拟机所属的主机"""
        url = common.CSERVER_HOST_URL % host_id
        req_content = self._request.getRequestInfo(url)
        if req_content and req_content.has_key("name"):
            return req_content["name"]
        return ""

    def get_vm_cpu_memory_usage(self, vm_id):
        """获取虚拟机的内存使用量"""
        total_memory = 0
        actual_memory = 0
        memory_usage = 0
        cpu_usage = 0
        
        req_content = self._request.getRequestInfo(common.CSERVER_VM_STATICS_URL % vm_id)
        if req_content and req_content.has_key("statistic"):
            for item in req_content["statistic"]:
                if item["name"] == "memory.installed":
                    values = item['values']["value"]
                    for value in  values :
                        if "datum" in value.keys():
                            total_memory = value['datum']
                elif item["name"] == "memory.used":
                    values = item['values']["value"]
                    for value in  values :
                        if "datum" in value.keys():
                            actual_memory = value['datum']
                elif item["name"] == "cpu.current.hypervisor":
                    values = item['values']["value"]
                    for value in  values :
                        if "datum" in value.keys():
                            cpu_usage = value['datum']
                
        if total_memory == 0 or actual_memory == 0:
            return cpu_usage, memory_usage
        
        memory_usage = float("%.2f" % ((actual_memory / (total_memory * 1.0)) * 100))
#         print "memory usage:", memory_usage, "cpu_usage:", cpu_usage
        return cpu_usage, memory_usage

    def get_vm_total_disk_size(self, vm_id):
        total_disk_size = 0
        req_content = self._request.getRequestInfo(common.CSERVER_VM_DISK_URL % vm_id)
        if req_content and req_content.has_key("disk"):
            for disk in req_content["disk"]:
                total_disk_size += disk["size"]
            
        return total_disk_size / 1024.0 / 1024.0 / 1024.0

    def get_vm_disk_usage(self, vm_id):
        """获取虚拟机的硬盘使用量"""
        total_disk_size = 0
        actual_disk_size = 0
        disk_usage = 0
        req_content = self._request.getRequestInfo(common.CSERVER_VM_DISK_URL % vm_id)
        if req_content and req_content.has_key("disk"):
            for disk in req_content["disk"]:
                total_disk_size += disk["size"]
                actual_disk_size += disk["actual_size"]
            
        if total_disk_size == 0:
            return disk_usage
        
        disk_usage = float("%.2f" % ((actual_disk_size / (total_disk_size * 1.0)) * 100))
        return  disk_usage
            
    def get_template_disk_size(self, template_id):
        template_size = 0
        req_content = self._request.getRequestInfo(common.CSERVER_TEMPLATE_URL % template_id)
#         print "template disk size", req_content
        if req_content and req_content.has_key("disk"):
            for disk in req_content["disk"]:
                template_size += disk["size"]
                
        return template_size / 1024.0 / 1024.0 / 1024.0
        
    def get_template_list(self):
        '''
        获取模板的列表信息
        '''
        template_list = []
        req_content = self._request.getRequestInfo(common.CSERVER_TEMPLATE_LIST_URL)
        if req_content and req_content.has_key("template"):
            for template in req_content["template"]:
                cores = int(template["cpu"]["topology"]["cores"])
                sockets = int(template["cpu"]["topology"]["sockets"])
                template_info = {}
                template_info["id"] = template["id"]
                template_info["name"] = template["name"]
                template_info["memory"] = template["memory"]/1024.0/1024.0
                template_info["ram"] = int(template["memory"]/1024.0/1024.0)
                template_disk_size = self.get_template_disk_size(template["id"])
                template_info["disk"] = template_disk_size if template_disk_size else 10.0
                template_info["cpu"] = int(cores * sockets)
                template_info["type"] = template["type"]
                template_info["os_type"] = template["os"]["type"]
                template_info["cluster_id"] = template["cluster"]["id"]
                template_list.append(template_info)
                
        return template_list
    
    
    