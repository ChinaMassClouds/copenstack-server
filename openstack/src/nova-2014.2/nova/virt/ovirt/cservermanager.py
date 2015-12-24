#coding:utf-8

from request import Request
import json
import time
import common
import utils
from db import CServerDatabase
from nova.openstack.common import log as logging

LOG = logging.getLogger(__name__)

class CServerManager(object):
    """
    cserver管理类
    """
    def __init__(self, address, username, password, domain="internal"):
        self._address = address
        self._username = username
        self._password = password
        
        self._request = Request(address, username, password, domain)
            
            
    def control_vm_action(self, uuid, action):
        """控制虚拟机开关机等操作"""
        vm_template = "<action><status></status><fault><reason></reason><detail></detail></fault></action>"
        url = "/massclouds-svmanager/api/" + 'vms/' + uuid+'/' + action
        try:
            respone = self._request.postRequestInfo(url,vm_template)
            if respone == False:
                return False
            else:
                return True
        except Exception:
            return False
        
        

    def spawn(self, vm_info):
        """创建虚拟机"""
        vm_template ='<vm><name>%s</name><cluster id = "%s"/><template id ="%s"/></vm>' % \
                    (vm_info["name"], vm_info["cluster_id"], vm_info["template_id"])
        url = "/massclouds-svmanager/api/vms"
        request_content = self._request.postRequestInfo(url,vm_template)
        if request_content:
            if 'id' in request_content.keys():
                vserver_vm_id = request_content.get("id")
                for i in range(60):
                    if self.is_create_vm_finish(vserver_vm_id):
                        vm_ip = self.get_vm_ip(vserver_vm_id)
                        flavor_id = vm_info["flavor_id"]
                        cserver_db = CServerDatabase(common.CServerDBConfig)
                        cserver_db.insert(common.INSERT_CSERVER_UUID_MAP_TABLE_SQL % (vm_info["uuid"], vserver_vm_id, vm_ip, flavor_id))
                        cserver_db.close()
                        self.control_vm_action(vserver_vm_id, "start")
                        return vserver_vm_id
                    time.sleep(5) 
                
        return ""
    
    
    def set_vm_ticket(self, vm_id):
        url = "/massclouds-svmanager/api/vms/%s/ticket" % vm_id
        ticket_content = "<action><ticket><value>123456</value><expiry>86400</expiry></ticket></action>"
        request_content = self._request.postRequestInfo(url, ticket_content)
        if not request_content:
            LOG.info("set vm %s ticket failed" % vm_id)
        return request_content
    
    def delete_vm(self, vm_uuid):
        """删除虚拟机"""
        url = "/massclouds-svmanager/api/vms/%s" % vm_uuid
        info = "<action><force>true</force></action>"
        power_state = self.get_vm_power_state(vm_uuid)
        if power_state == 1 or power_state == 7:
            self.control_vm_action(vm_uuid, "stop")
            for i in range(30):
                if self.get_vm_power_state(vm_uuid) == 4:
                    self._request.deleteRequestInfo(url, info)
                    return
                time.sleep(5)
        else:
            self._request.deleteRequestInfo(url, info)
            
        
    def get_cserver_uuid_map(self, cserver_uuid):
        """得到cserver的虚拟机的uuid影射"""
        cserver_db = CServerDatabase(common.CServerDBConfig)
        cserver_db.query(common.SELECT_CSERVER_UUID_MAP_TABLE_SQL % cserver_uuid)
        cserver_uuid = cserver_db.fetchOneRow()
        if cserver_uuid:
            return cserver_uuid[0]
        
        return ""

    def is_create_vm_finish(self, vm_id):
        """判断虚拟机是否创建完成"""
        url = "/massclouds-svmanager/api/vms/%s/disks" % vm_id
        request_content = self._request.getRequestInfo(url)
        if request_content:
            for disk in request_content["disk"]:
                if disk["status"]["state"] == "ok":
                    return True
        return False
    
    def get_total_memory(self):
        """得到cserver的总的内存"""
        totalMemory = 0
        url = '/massclouds-svmanager/api/hosts'
        request_content = self._request.getRequestInfo(url)
        if request_content:
            for host in request_content["host"]:
                totalMemory += self.get_host_total_memory(host["id"])
        return totalMemory/1024/1024

    def get_vm_vnc_host_port(self, vm_uuid):
        """得到虚拟机的所在的主机和端口号"""
        host = ""
        port = ""
        
        url = '/massclouds-svmanager/api/vms/'+vm_uuid
        request_content = self._request.getRequestInfo(url)
        if request_content:
            display_type = request_content["display"]["type"]
            if display_type == "vnc":
                host = request_content["display"]["address"]
                port = request_content["display"]["port"]
                print host, port
            
        return host, port

    def get_vm_ip(self, vm_uuid):
        """得到虚拟机的IP地址"""
        vm_ip = ""
        
        url = '/massclouds-svmanager/api/vms/'+vm_uuid
        request_content = self._request.getRequestInfo(url)
        if request_content:
            if request_content.has_key("guest_info"):
                ip_list = request_content["guest_info"]["ips"]["ip"]
                if ip_list and ip_list[0].has_key("address"):
                    vm_ip = ip_list[0]["address"]
            
        return vm_ip
        
    def get_vm_power_state(self, uuid):
        """得到虚拟机的电源状态"""
        url = '/massclouds-svmanager/api/vms/'+uuid
        request_content = self._request.getRequestInfo(url)
        if request_content:
            vm_state = request_content["status"]["state"]
            return common.CSERVER_POWER_STATE.get(vm_state, 0)
            
        return common.CSERVER_POWER_STATE[common.UNKNOWN]
        
    def get_host_total_memory(self, host_id):
        """得到主机的总的内存"""
        url = '/massclouds-svmanager/api/hosts/' + host_id + '/statistics'
        request_content = self._request.getRequestInfo(url)
        if request_content:
            for info in request_content["statistic"]:
                if info['name'] =='memory.total':
                    val_list = info['values']['value']
                    for val in val_list :
                        if 'datum' in val.keys():
                            return val['datum']    
        return 0   

        
