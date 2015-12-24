#coding:utf-8

from exception import LoginVCenterFailed, NoveComputeServiceFailed, ImageNotFound, \
                      LoginCServerFailed, RequestError
import paramiko, uuid, json
import MySQLdb
from cserver import CSeverPlatformManager
from vcenter import VCenterPlatformManager
from logrecord import log
import threading
import time 

class HeterogeneousPlatformManager(object):
    _instance = None
    """
    接管异构平台管理器
    支持接管平台类型： cserver, vcenter
    """
    def __init__(self):
        self._vcenterPFM = VCenterPlatformManager()
        self._CSeverPFM = CSeverPlatformManager()
        self._is_auto = False
        self._is_deleting = False
        
        sync_threading = threading.Thread(target=self.auto_synchronism)
        sync_threading.start()
        
        sync_threading = threading.Thread(target=self.auto_record_cserver_monitor_info)
        sync_threading.start()
        
    def auto_synchronism(self): 
        while True:
            time.sleep(600)
            if not self._is_deleting:
                print "start synchronism............"
                log.logger.info("start synchronism............")
                self._is_auto = True
                for manager in [self._vcenterPFM, self._CSeverPFM]:
                    manager.auto_synchronism()
            self._is_auto = False
            print "stop synchronism.............."
            log.logger.info("stop synchronism..............")
            
    def auto_record_cserver_monitor_info(self):
        while True:
            time.sleep(300)
            print "record............"
            log.logger.info("record............")
            self._CSeverPFM.record_cserver_monitor_info()
            time.sleep(300)
            
        
    @staticmethod
    def instance():
        if HeterogeneousPlatformManager._instance is None:
            HeterogeneousPlatformManager._instance = HeterogeneousPlatformManager()
            
        return HeterogeneousPlatformManager._instance
    
    def get_platform_dcbase_info(self, platform_info):
        """
        获取异构平台的数据中心集群基础信息
        
        _@platform_info:平台实例的基础信息,集群的用户名，密码和地址信息
        _@return: 例： {
                     'datacenter1':['cluster-1', 'cluster-2',], 
                     'datacenter2':['cluster-3', 'cluster-4'], 
                    }
        """
        try:
            if platform_info["virtualplatformtype"] == "vcenter":
                return self._vcenterPFM.get_platform_base_info(platform_info)
            elif platform_info["virtualplatformtype"] == "cserver":
                return self._CSeverPFM.get_platform_base_info(platform_info)
        except LoginVCenterFailed as e:
            log.logger.error("LoginVCenterFailed, errormsg: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except RequestError as e:
            log.logger.error("RequestError, errormsg: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
            
    def add_heterogeneous_platform_instance(self, platform_info):
        """
        添加异构平台实例
        _@platform_info:要添加的平台实例的基础信息,集群的用户名，密码和地址信息，接管集群等
        """
        try:
            print "platform_info:", platform_info
            if platform_info["virtualplatformtype"] == "vcenter":
                self._vcenterPFM.add_vcenter_platform_instance(platform_info)
            elif platform_info["virtualplatformtype"] == "cserver":
                self._CSeverPFM.add_CSever_platform_instance(platform_info)
            return {"action": "success"}
        except LoginVCenterFailed as e:
            log.logger.error("LoginVCenterFailed, errormsg: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except LoginCServerFailed as e:
            log.logger.error("LoginCServerFailed, errormsg: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except RequestError as e:
            log.logger.error("RequestError, errormsg: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except paramiko.ssh_exception.AuthenticationException as e:
            print "paramiko.ssh_exception.AuthenticationException"
            log.logger.error("paramiko.ssh_exception.AuthenticationException, errormsg: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except NoveComputeServiceFailed as e:
            log.logger.error("NoveComputeServiceFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except ImageNotFound as e:
            log.logger.error("ImageNotFound: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
        
        
    def remove_heterogeneous_platform_instance(self, platform_info):
        """
        删除异构平台实例
        _@platform_uuid:要删除的平台实例的uuid
        """
        try:
            if self._is_auto:
                self._is_deleting = False
                return {"action": "failed", "errormsg": "plafrom is synchronism", "is_auto": True}
            
            self._is_deleting = True
            print "remove..............."
            if platform_info["virtualplatformtype"] == "vcenter":
                self._vcenterPFM.remove_vcenter_platform_instance(platform_info)
            elif platform_info["virtualplatformtype"] == "cserver":
                self._CSeverPFM.remove_csever_platform_instance(platform_info)
            self._is_deleting = False
            
            return {"action": "success"}
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            self._is_deleting = False
            error = {"action": "failed", "errormsg": errmsg}
            return error
        except:
            self._is_deleting = False
        
    def sync_heterogeneous_platform_instance(self, platform_info):
        try:
            if platform_info["virtualplatformtype"] == "vcenter":
                self._vcenterPFM.sync_vcenter_instance(platform_info)
            elif platform_info["virtualplatformtype"] == "cserver":
                self._CSeverPFM.sync_cserver_instance(platform_info)
            return {"action": "success"}
        except ImageNotFound as e:
            log.logger.error("ImageNotFound: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except RequestError as e:
            log.logger.error("RequestError: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
        
    def edit_heterogeneous_platform_instance(self, platform_info):
        """
        编辑异构平台实例
        _@platform_info:平台实例的基础信息,集群的用户名，密码和地址信息，接管集群等
        """
        self._vcenterPFM.edit_vcenter_instance(platform_info)
        
        
    def get_heterogeneous_platform_instances(self):
        """
        获取异构平台实例列表
        """
        try:
            platform_instances_info = []
            for manager in [self._vcenterPFM, self._CSeverPFM]:
                platform_instances_info.extend(manager.get_platform_instances_info())
            return platform_instances_info
        except LoginVCenterFailed as e:
            log.logger.error("LoginVCenterFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except LoginCServerFailed as e:
            log.logger.error("LoginCServerFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except RequestError as e:
            log.logger.error("RequestError: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
        
        
    def get_allhp_datacenter_info(self):
        """
        获取所有异构平台实例的数据中心信息
        """
        try:
            datacenter_info = []
            for manager in [self._vcenterPFM, self._CSeverPFM]:
                datacenter_info.extend(manager.get_datacenter_info_list())
            return datacenter_info
        except LoginVCenterFailed as e:
            log.logger.error("LoginVCenterFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}      
            return error
        except LoginCServerFailed as e:
            log.logger.error("LoginCServerFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except RequestError as e:
            log.logger.error("RequestError: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
        
    def get_allhp_cluster_info(self):
        """
        获取所有异构平台实例的集群信息
        """
        try:
            cluster_info = []
            for manager in [self._vcenterPFM, self._CSeverPFM]:
                cluster_info.extend(manager.get_cluster_info_list())
            return cluster_info
        except LoginVCenterFailed as e:
            log.logger.error("LoginVCenterFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except LoginCServerFailed as e:
            log.logger.error("LoginCServerFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except RequestError as e:
            log.logger.error("RequestError: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
    
    def get_allhp_host_info(self):
        """
        获取所有异构平台实例的主机信息
        """
        try:
            host_info = []
            for manager in [self._vcenterPFM, self._CSeverPFM]:
                host_info.extend(manager.get_host_info())
            print host_info
            return host_info
        except LoginVCenterFailed as e:
            log.logger.error("LoginVCenterFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except LoginCServerFailed as e:
            log.logger.error("LoginCServerFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except RequestError as e:
            log.logger.error("RequestError: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
            
    def get_vcenter_vm_list(self, platfrom_info):
        try:
            vm_info_list = self._vcenterPFM.get_vm_info_list(platfrom_info["name"])
            print vm_info_list
            return vm_info_list
        except RequestError as e:
            log.logger.error("RequestError: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except LoginCServerFailed as e:
            log.logger.error("LoginCServerFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
            
    def get_cserver_vm_list(self, platfrom_info):
        try:
            vm_info_list = self._CSeverPFM.get_vm_info_list(platfrom_info["name"])
            print vm_info_list
            return vm_info_list
        except RequestError as e:
            log.logger.error("RequestError: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except LoginCServerFailed as e:
            log.logger.error("LoginCServerFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
        
    def get_cserver_template_list(self, platfrom_info):
        try:
            template_list = self._CSeverPFM.get_template_list(platfrom_info["name"])
            print template_list
            return template_list
        except RequestError as e:
            log.logger.error("RequestError: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except LoginCServerFailed as e:
            log.logger.error("LoginCServerFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
        
    def get_cserver_cluster_info_list(self, platfrom_info):
        try:
            cluster_info_list = self._CSeverPFM.get_specity_platform_cluster_info_list(platfrom_info)
            print cluster_info_list
            return cluster_info_list
        except RequestError as e:
            log.logger.error("RequestError: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except LoginCServerFailed as e:
            log.logger.error("LoginCServerFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
        
    def get_cserver_uuid_maps_info(self):
        try:
            cserver_uuid_maps = self._CSeverPFM.get_cserver_uuid_maps_info()
#             print cserver_uuid_maps
            return cserver_uuid_maps
        except RequestError as e:
            log.logger.error("RequestError: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
        
    def get_vcenter_uuid_maps_info(self):
        try:
            vcenter_uuid_maps = self._vcenterPFM.get_vcenter_uuid_maps_info()
            print vcenter_uuid_maps
            return vcenter_uuid_maps
        except RequestError as e:
            log.logger.error("RequestError: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
            
    def get_specify_platform_instance_info(self, platform_uuid):
        try:
            platform_info = []
            for manager in [self._vcenterPFM, self._CSeverPFM]:
                platform_info.append(manager.get_specify_platform_instance_info(platform_uuid))
            print platform_info
            return platform_info
        except RequestError as e:
            log.logger.error("RequestError: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except LoginCServerFailed as e:
            log.logger.error("LoginCServerFailed: %s" % e.msg)
            error = {"action": "failed", "errormsg": e.msg}
            return error
        except MySQLdb.Error, e:
            errmsg = json.dumps(e.args)
            log.logger.error("MySQL error, errormsg: %s" % errmsg)
            error = {"action": "failed", "errormsg": errmsg}
            return error
        
# if __name__ == '__main__':
#     vcenter_platform_info = {
#                      'name': 'byq_platform1',
#                      'domain_name': 'zonea',
#                      'hostname': 'byqcontroller.localdomain',
#                      'tenantname': 'admin',
#                      'username': 'admin',
#                      'passwd': 'admin',
#                      'network_id': 'e3cb3245-d389-4a1c-82e6-6a88c85fcf9f',
#                      'virtualplatformIP': '192.168.15.100',
#                      'virtualplatformusername': 'administrator@ vsphere.local',
#                      'virtualplatformpassword': 'Byq@123456',
#                      'uuid': 'b3d1432d-5684-49cf-aa48-cf6840d88ab8',
#                      'virtualplatformtype': 'vcenter',
#                      "datacentersandclusters": {"Datacenter": ["cluster"]}
#                      }
#       
#     vcenter_info = {u'username': u'admin', 
#                     u'virtualplatformusername': u'administrator@vsphere.local', 
#                     u'name': u'abc_vcenter', 
#                     u'virtualplatformIP': u'192.168.15.100', 
#                     u'passwd': u'admin', 
#                     u'hostname': u'byqcontroller.localdomain', 
#                     u'domain_name': u'zonea', 
#                     u'virtualplatformpassword': u'Byq@123456', 
#                     u'network_id': u'e3cb3245-d389-4a1c-82e6-6a88c85fcf9f', 
#                     "datacentersandclusters": {"Datacenter": ["cluster"]},
#                     u'tenantname': u'admin', u'virtualplatformtype': u'vcenter'}
#                   
#     cserver_platform_info = {
#                      'name': 'cserver',
#                      'domain_name': 'zonea',
#                      'hostname': 'byqcontroller.localdomain',
#                      'tenantname': 'admin',
#                      'username': 'admin',
#                      'passwd': 'admin',
#                      'network_id': 'e3cb3245-d389-4a1c-82e6-6a88c85fcf9f',
#                      'virtualplatformIP': '192.168.15.150',
#                      'virtualplatformusername': 'sysadmin',
#                      'virtualplatformpassword': 'admin==1',
#                      'uuid': '80275fae-35e0-4036-8b71-18a0aa11d96d',
#                      'virtualplatformtype': 'cserver',
#                      "datacentersandclusters": {'Default': ['Default'], 'local': ['cluster-test']},
# #                      'vm_uuid_list': ['a6b9f3b7-d9fc-4d79-9524-b309e3fbefdf',],
#                      }
#     HeterogeneousPlatformManager.instance().get_platform_dcbase_info(vcenter_info)
#     HeterogeneousPlatformManager.instance().get_allhp_host_info()
#     HeterogeneousPlatformManager.instance().get_allhp_cluster_info()
#     HeterogeneousPlatformManager.instance().get_allhp_datacenter_info()
#     HeterogeneousPlatformManager.instance().add_heterogeneous_platform_instance(vcenter_info)
#     HeterogeneousPlatformManager.instance().get_heterogeneous_platform_instances()
#     HeterogeneousPlatformManager.instance().remove_heterogeneous_platform_instance(cserver_platform_info)
#     HeterogeneousPlatformManager.instance().sync_heterogeneous_platform_instance(cserver_platform_info)
#     HeterogeneousPlatformManager.instance().get_cserver_template_list(cserver_platform_info)
    
#     HeterogeneousPlatformManager.instance().get_cserver_cluster_info_list(cserver_platform_info)
    
#     HeterogeneousPlatformManager.instance().get_specify_platform_instance_info('93c0629d-7a7c-46da-a9a2-f0c39207586d')

#     HeterogeneousPlatformManager.instance().get_cserver_uuid_maps_info()
#     HeterogeneousPlatformManager.instance().get_cserver_vm_list(cserver_platform_info)
#     HeterogeneousPlatformManager.instance().auto_record_cserver_monitor_info()
#     HeterogeneousPlatformManager().get_vcenter_uuid_maps_info()
         
