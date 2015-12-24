# -*- coding: utf-8 -*-
import requests
import json, time
import uuid, os
from platforms import common
from exception import RequestError, RequestConnectError, ImageNotFound
from db.mysql import NovaDatabase, PlatformDatabase
from db.novdb_utils import NovaDatabaseUtils
from db.common import NovaDBConfig, CServerDBConfig, PlatformDBConfig, VCenterDBConfig
import db
import threading
from logrecord import log


class VMTakeoverTools(object):
    """虚拟机接管工具类"""
    _instance = 0
    def __init__(self,host, tenant_name, username, password):
        super(VMTakeoverTools,self).__init__()
        self._host  = host 
        self._tenant_name = tenant_name
        self._username = username
        self._password = password
        self._tenant_id = ""
        
        self.headers = {
                        'Host': 'identity.api.openstack.org',
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'Accept-Encoding': 'gzip, deflate',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Cookie': 'username=root; kimchiLang=zh_CN',
                        'X-Requested-With': 'XMLHttpRequest',
                                }
        self.currentTenantName = ""
        self.openstackServiceHostMap = {}

    def setOpenstackServiceHost(self, accessInfo):
    
        if not accessInfo:
            return
        
        if accessInfo.get("access", None) is None:
            return
        
        if accessInfo["access"].get("serviceCatalog", None) is None:
            return
        
        endPoints = accessInfo["access"]["serviceCatalog"]
    
        for subEndPoint in endPoints:
            if subEndPoint.get("endpoints", None) is None:
                continue
            
            for url in subEndPoint["endpoints"]:
                adminURL = url["adminURL"]
                address = adminURL.split(":")[1][2:]
                port = adminURL.split(":")[2].split('/')[0]
                self.openstackServiceHostMap[port] = address
        

    def getAuthToken(self):
        """
        获取认证
        """
      
        urlPath = "http://" + self._host + ":5000/v2.0/tokens"
        payload = {
                    "auth": {
                        "tenantName": self._tenant_name,
                        "passwordCredentials": {
                            "username":self._username,
                            "password":self._password,
                                                 }
                                    }
                        }
        
        try:
            r = requests.post(urlPath, data=json.dumps(payload), headers=self.headers)
            if r.ok:
                self.currentTenantName = self._tenant_name
                infoDict = r.json()
                self.setOpenstackServiceHost(infoDict)
                self.headers.update({'X-Auth-Token': infoDict["access"]["token"]["id"]})
                return infoDict
            else:
                raise RequestError(urlPath + " " + r.content)
        except requests.exceptions.ConnectionError, e:
            raise RequestConnectError(e.msg)
        except Exception, e:
            raise RequestError(e.msg)
        

    def getServiceURL(self, url):
        return "http://" + self._host + ":" + url


        
    def getRequestInfo(self, url):
        """
        获取请求的信息
        @url 请求的url信息
        """
        try:
            if not self.currentTenantName or self.currentTenantName != self._tenant_name:
                self.getAuthToken()
                request = requests.get(self.getServiceURL(url), headers=self.headers)
            else:        
                request = requests.get(self.getServiceURL(url), headers=self.headers)
                if not request.ok and request.content == common.authFailMsg:
                    self.getAuthToken()
                    request = requests.get(self.getServiceURL(url), headers=self.headers)
                    
            if request.ok:
                return request.json()
            else:
                log.logger.error("Get request failed: %s, url: %s" % (request.content, url))
                raise RequestError(url + " " + request.content)
            
        except requests.exceptions.ConnectionError, e:
            log.logger.error("Get request connect failed, url: %s" % url)
            raise RequestConnectError(e.msg)
        
        
        
    def postRequestInfo(self, url, info, isNeedReturnValue=False):
        """
        执行相应的请求操作
        @url 请求的url信息，
        @info 执行操作时需要的数据
        @isNeedReturnValue 执行完操作时，是否需要返回相应的信息
        """
        try:
            if not self.currentTenantName or self.currentTenantName != self._tenant_name:
                self.getAuthToken()
                request = requests.post(self.getServiceURL(url), data=json.dumps(info), headers=self.headers)
            else:
                request = requests.post(self.getServiceURL(url), data=json.dumps(info), headers=self.headers)
                if not request.ok and request.content == common.authFailMsg:
                    request = requests.post(self.getServiceURL(url), data=json.dumps(info), headers=self.headers)
          
            if not request.ok:
                log.logger.error("Post request failed: %s, url: %s" % (request.content, url))
                raise RequestError(url + " " + request.content)  
            
            if request.ok and isNeedReturnValue:
                return request.json()
            
            if request.ok and not isNeedReturnValue:
                return True
        except requests.exceptions.ConnectionError, e:
            log.logger.error("Post request connect failed, url: %s" % url)
            raise RequestConnectError(e.msg)
         
        return False
    
        
    def deleteRequestInfo(self, url, isNeedReturnValue=False):
        """
        执行相应的删除请求操作
        @url 请求的url信息，
        @isNeedReturnValue 执行完操作时，是否需要返回相应的信息
        """
        try:
            if not self.currentTenantName or self.currentTenantName != self._tenant_name:
                self.getAuthToken()
                request = requests.delete(self.getServiceURL(url), headers=self.headers)
            else:
                request = requests.delete(self.getServiceURL(url),headers=self.headers)
                if not request.ok and request.content == common.authFailMsg:
                    self.getAuthToken()
                    request = requests.delete(self.getServiceURL(url), headers=self.headers)
                 
            if not request.ok:
#                 print request.content
                log.logger.error("Delete request failed: %s, url: %s" % (request.content, url))
                raise RequestError(url + " " + request.content)  
            
            if request.ok and isNeedReturnValue:
                return request.json()
            
            if request.ok and not isNeedReturnValue:
                return True
            
        except requests.exceptions.ConnectionError, e:
            log.logger.error("Delete request connect failed, url: %s" % url)
            raise RequestConnectError(e.msg)
        
        return False
        
        
        
    def putRequestInfo(self, url, info, isNeedReturnValue=False):
        try:
            if not self.currentTenantName or self.currentTenantName != self._tenant_name:
                self.getAuthToken()
                request = requests.put(self.getServiceURL(url), data=json.dumps(info), headers=self.headers)
            else:
                request = requests.put(self.getServiceURL(url), data=json.dumps(info), headers=self.headers)
                if not request.ok and request.content == common.authFailMsg:
                    self.getAuthToken()
                    request = requests.put(self.getServiceURL(url), data=json.dumps(info), headers=self.headers)
            if not request.ok:
                log.logger.error("Put request failed: %s, url: %s" % (request.content, url))
                raise RequestError(url + " " + request.content) 
             
            if request.ok and isNeedReturnValue:
                return request.json()
            
            if request.ok and not isNeedReturnValue:
                return True
        except requests.exceptions.ConnectionError, e:
            log.logger.error("Put request connect failed, url: %s" % url)
            raise RequestConnectError(e.msg)
            
        return False
        
   
    def get_tenant_id(self):
        '''
        获取租户ID
        :return 租户ID
        '''
        if not self._tenant_id:
            tenantInfo = self.getRequestInfo(common.TENANT_URL)
            list_tenant = tenantInfo['tenants']
            for tenant in list_tenant:
                if tenant['name'] == self._tenant_name:
                    self._tenant_id = tenant['id']
        return self._tenant_id
    
          
    def get_local_flavor(self):
        '''
        获取openstack 上指定租户的所有flavor
        :return  租户下所有的flavor列表
        '''
        flavor_info_list = []
        tenantId = self.get_tenant_id()
        if not tenantId:
            return flavor_info_list
        
        flavor_details_url = common.FLAVOR_DETAILS_URL % tenantId
        flavor_list = self.getRequestInfo(flavor_details_url)["flavors"]
        for flavor in flavor_list:
            flavor_info_list.append({"id": flavor["id"], "name": flavor["name"], "ram": flavor["ram"], "vcpus": flavor["vcpus"], "disk": flavor["disk"]})
        return flavor_info_list
    
    
    def create_specific_flavor(self,new_flavor_info):
        '''
        创建指定的 flavor
        :param new_flavor_info: 要创建的flavor的配置信息
        '''
        
        flavor ={
                    "flavor":{
                                  "name":new_flavor_info["name"],
                                  "ram":new_flavor_info["ram"],
                                  "vcpus":new_flavor_info["vcpus"],
                                  "disk":new_flavor_info["disk"],
                                  "id":new_flavor_info["id"]
                              }
                 }
        tenantId = self.get_tenant_id()
        flavor_url = common.FLAVORS_ID_URL % tenantId
        return self.postRequestInfo(flavor_url,flavor)
        
    def get_image_id(self, image_type):
        '''
        获取镜像的ID
        :param image_type: 镜像的类型
        :return 镜像的ID
        '''
#         tenantId = self.get_tenant_id(tenantName, username, passwd)
#         image_url = common.IMAGE_URL % tenantId
#           
#         images_info = self.getRequestInfo(image_url, tenantName, username, passwd)
# #         print "images_list:", images_list
#         if images_info.has_key("images"):
#             for image in images_info["images"]:
#                 if image["name"] == "cirros-trusty-cloud":
#                     return image["id"]
        
        image_type_map = {"vcenter": 'vmdk', 'cserver': 'qcow2'}
        
        GET_ALL_IMAGE ="9292/v1/images/detail?sort_key=name&sort_dir=asc&limit=20"
        request_info = self.getRequestInfo(GET_ALL_IMAGE)
        if request_info.has_key("images"):
            list_images = request_info["images"]
            for images in list_images:
                if images.get("disk_format") == image_type_map[image_type]:
                    if images.get("name") == "cserver_template_image":
                        return images.get("id")
                    elif images.get("name") == "vcenter_template_image":
                        return images.get("id")
        return ""
    
        
    def _create_new_vm(self, ptype, vm_info, image_id, flavor_id, zone, network_id):
        '''
        接管异构平台 的现有主机工具
       :param vm_info :虚拟机的信息
       :param imageRef :镜像的ID
       :param flavor:flavor 的ID
       :param zone :可用域
       :param networkId :虚拟机网络信息 [{"uuid":id}]
        '''
#         
        print "vmname:", vm_info["name"], "flavorid:", flavor_id
        vm = {
          "server": {
                     "networks":[{"uuid": str(network_id)}],
                     "name": str(vm_info["name"]),
                     "availability_zone": str(zone),
                     "imageRef":"http://" + self._host + "/images/" + str(image_id),
                     "flavorRef":"http://"+self._host + "/flavors/" + str(flavor_id),
                     "metadata": {
                                 "load_vcenter_vm": "true",
                                 "platformtype": ptype,
                                 "uuid": str(vm_info["id"]),
                                },
                     "min_count": "1",
                     "max_count": "1",
                                }
  
                }
        
        tenantId = self.get_tenant_id()
        url = common.SERVER_URL % tenantId
        flag =self.postRequestInfo(url,  vm)
        print "flag",flag
        return flag
        
    def _add_vm(self, ptype, vm_info, zone, network_id, image_id, hostname):
        '''
        :param ptype: 异构平台的类型
        :param platfrom_vms_list: 异构平台的虚拟机列表
        :param hostname: 接管异构平台的主机名
        :param zone: 接管异构平台的所属域
        :param network_id: 异构平台所属的网络ID
        '''
        flavor_id = self.get_vm_flavor_id(vm_info)
        
        #如果异构平台的类型为cserver则将虚拟机在cserver端和在openstack端的uuid影射关系写入数据库
        if ptype == "cserver":
            cserver_flavor_id = self.get_cserver_flavor_id()
            cserver_db = PlatformDatabase(CServerDBConfig)
            openstack_uuid = cserver_uuid = vm_info["id"]
            vm_ip = vm_info["ip"]
            sql = db.common.INSERT_CSERVER_UUID_MAP_TABLE_SQL % (openstack_uuid, cserver_uuid, vm_ip, flavor_id)
            cserver_db.insert(sql)
            cserver_db.close()
            
            self._create_new_vm(ptype, vm_info, image_id, cserver_flavor_id, zone, network_id)
        elif ptype == "vcenter":
            vcenter_flavor_id = self.get_vcenter_flavor_id()
            vcenter_db = PlatformDatabase(VCenterDBConfig)
            openstack_uuid = vcenter_uuid = vm_info["id"]
            vm_ip = ""
            sql = db.common.INSERT_VCENTER_UUID_MAP_TABLE_SQL % (openstack_uuid, vcenter_uuid, vm_ip, flavor_id)
            vcenter_db.insert(sql)
            vcenter_db.close()
            self._create_new_vm(ptype, vm_info, image_id, vcenter_flavor_id, zone, network_id)
        else:
            #在本地创建新的虚拟机
            self._create_new_vm(ptype, vm_info, image_id, flavor_id, zone, network_id)
         
        for i in range(60):
            time.sleep(1)
            db_util = NovaDatabaseUtils()
            vm_state = db_util.query_vm_state(vm_info["id"])
            #如果虚拟机的状态为error，则同步数据库中的虚拟机的主机名
            if vm_state and vm_state[0] == 'error':
                log.logger.info("create new vm failed, vm state is 'error'")
                self._sync_vm_hostname(vm_info, hostname)
                return
            
            #构建完成后，同步虚拟机的状态和去除元数据
            if vm_state and vm_state[0] != "building":
                self._sync_vm_state(ptype, vm_info)
                self._reset_vm_metadata(vm_info["id"])
                return
        
    
    def _sync_vm_hostname(self, vm_info, hostname):
        '''
        同步数据库中的虚拟机的主机名
        :param vm_info: 虚拟机的信息
        :param hostname: 虚拟机的主机名
        '''
        db_con = NovaDatabase(NovaDBConfig)
        sql = "update instances set host='%s' where uuid='%s';" % \
                     (hostname, vm_info["id"])
        db_con.update(sql)
        db_con.commit()
        db_con.close()
        
    def _sync_vm_state(self, ptype, vm_info):
        '''
        同步数据库中的虚拟机的主机名
        :param ptype: 异构平台的类型
        :param vm_info: 虚拟机的信息
        '''
        vm_state = "active"
        power_state = 1
        
        if ptype == "vcenter":
            if vm_info["power_state"] == "poweredOff":
                vm_state = "stopped"
                power_state = 4
            if vm_info["power_state"] == "poweredOn":
                vm_state = "active"
                power_state = 1
            elif vm_info["power_state"] == "suspended":
                vm_state = "suspended"
                power_state = 7
        elif ptype == "cserver":
            if vm_info["power_state"] == "down":
                vm_state = "stopped"
                power_state = 4
            elif vm_info["power_state"] == "suspended":
                vm_state = "suspended"
                power_state = 7
            elif vm_info["power_state"] == "up":
                vm_state = "active"
                power_state = 1
        
        db_con = NovaDatabase(NovaDBConfig)
        sql = "update instances set display_name='%s', vm_state='%s', power_state=%s, task_state=NULL where uuid='%s';" % \
                     (vm_info['name'], vm_state, power_state, vm_info["id"])
        db_con.update(sql)
        db_con.commit()
        db_con.close()
        
                
    def is_create_specific_flavor(self,vm_info):
        '''
        判断是否创建特定的flavor
        :param  vm_info: 虚拟机的信息
        :return 如果需要创建返回True 否则返回(False, flavor_id)
        '''
        vm_flavor={"ram": vm_info["ram"], "vcpus": vm_info["cpu"], "disk": int(vm_info["disk"])}
        for local_flavor in self.get_local_flavor():
            if vm_flavor["ram"] == local_flavor["ram"] and vm_flavor["vcpus"] == local_flavor["vcpus"] \
                    and vm_flavor["disk"] == local_flavor["disk"]:
                return False, local_flavor["id"]

        return True, None
    
    def get_cserver_flavor_id(self):
        for local_flavor in self.get_local_flavor():
            if local_flavor["name"] == "m1.cserver_flavor":
                return local_flavor["id"]
        
        return ""
    
    def get_vcenter_flavor_id(self):
        for local_flavor in self.get_local_flavor():
            if local_flavor["name"] == "m1.vcenter_flavor":
                return local_flavor["id"]
        
        return ""
    
    def get_vm_flavor_id(self, vm_info):
        """根据虚拟机的配置信息返回对于的flavor的ID
        :param  vm_info: 虚拟机的信息
        """
        is_create, flavor_id = self.is_create_specific_flavor(vm_info)
        if is_create:
            return "1"
        
        return flavor_id
    
    def _reset_vm_metadata(self,server_id):
        '''
        更新虚拟机metadata
        :param serverId : 虚拟机ID
        '''
        tenantId = self.get_tenant_id()
        DELETE_TAG = common.SERVER_METADATA_URL %(tenantId,server_id)
        self.deleteRequestInfo(DELETE_TAG)
    
    def get_local_vm_instances(self):
        '''
        获取openstack 上指定租户的所有的虚拟机
        :return  租户下所有的虚拟机列表
        '''
        vm_info_list = []
        vm_uuid_list = []
        tenantId = self.get_tenant_id()
        url =  common.SERVER_URL % tenantId
        req_content = self.getRequestInfo(url)
        if req_content.has_key("servers"):
            for server in req_content["servers"]:
                vm_info_list.append({"name":server["name"],"id":server["id"]})
                vm_uuid_list.append(server["id"])
        
#         print "vm_info_lists:", vm_info_list
        return vm_info_list, vm_uuid_list
    
    
    def delete_platform_instances(self, ptype, hostname):
        """删除异构平台上的虚拟机在本地的记录
        :param ptype: 异构平台的类型
        :param vm_info: 虚拟机的信息
        """
        db_util = NovaDatabaseUtils()
        plaform_db = ""
        del_sql = ""
        if ptype == "cserver":
            plaform_db = PlatformDatabase(CServerDBConfig)
            del_sql = db.common.DELETE_CSERVER_UUID_MAP_TABLE_SQL
        elif ptype == "vcenter":
            plaform_db = PlatformDatabase(VCenterDBConfig)
            del_sql = db.common.DELETE_VCENTER_UUID_MAP_TABLE_SQL
            
        if not plaform_db:
            log.logger.info("the platform type is error: %s" % ptype)
            return
            
        local_vm_list = db_util.get_vm_info_list(hostname)
        for vm in local_vm_list:
            log.logger.info("Delete local vm: %s, uuid: %s" % (vm["name"], vm["id"]))
            self._delete_local_instance(ptype, vm)
            os.system("/usr/local/bin/deletevm.sh %s" % vm["id"])
            openstack_uuid = vm["id"]
            sql = del_sql % openstack_uuid
            plaform_db.delete(sql)
        plaform_db.close()
    
    def _delete_local_instance(self, ptype, vm_info):
        """根据虚拟机的信息删除在本地平台的记录
        :param ptype: 异构平台的类型
        :param vm_info: 虚拟机的信息
        """
        tenant_id = self.get_tenant_id()
        user_id = vm_info["user_id"]
        
        #根据租户ID和用户ID查询资源的使用额
        db_util = NovaDatabaseUtils()
        instance_usage, ram_usage, cores_usage = db_util.query_resource_usage(tenant_id, user_id)
        vm_ram = vm_info["ram"]
        vm_cores = vm_info["vcpus"]
        print instance_usage, ram_usage, cores_usage
        
        #根据租户ID和用户ID更新资源的使用额
        if instance_usage and ram_usage and cores_usage:
            new_instance_usage = instance_usage - 1
            new_ram_usage = int(ram_usage) - int(vm_ram)
            new_cores_usage = int(cores_usage) - int(vm_cores)
            
            if new_instance_usage >= 0 and new_ram_usage >= 0 and new_cores_usage >= 0:
                db_util.update_resource_usage(tenant_id, user_id, new_instance_usage, new_ram_usage, new_cores_usage)
        
#         self._delete_instance_db(ptype, vm_info["id"])
            
            
    def _delete_instance_db(self, ptype, vm_id):
        """根据虚拟机的id从数据库中进行删除
        :param ptype: 异构平台的类型
        :param vm_id: 虚拟机的ID
        """
        os.system("/usr/local/bin/deletevm.sh %s" % vm_id)
        openstack_uuid = vm_id
        if ptype == "cserver":
            cserver_db = PlatformDatabase(CServerDBConfig)
            sql = db.common.DELETE_CSERVER_UUID_MAP_TABLE_SQL % openstack_uuid
            cserver_db.delete(sql)
            cserver_db.close()
        elif ptype == "vcenter":
            vcenter_db = PlatformDatabase(VCenterDBConfig)
            sql = db.common.DELETE_VCENTER_UUID_MAP_TABLE_SQL % openstack_uuid
            vcenter_db.delete(sql)
            vcenter_db.close()
            
    def check_create_new_flavor(self, platform_vm_info):
        """
        检测是否创建新的flavor
        :param platform_vm_info: 异构平台虚拟机信息
        """
        is_create, flavor_id = self.is_create_specific_flavor(platform_vm_info)
        if is_create:
            print "create new flavor........"
            new_flavor_info = {}
            new_flavor_info["id"] = str(uuid.uuid4())
            new_flavor_info["name"] = "vflavor-" + new_flavor_info["id"]
            new_flavor_info["ram"] = platform_vm_info["ram"]
            new_flavor_info["vcpus"] = platform_vm_info["cpu"]
            new_flavor_info['disk'] = int(platform_vm_info["disk"])
            self.create_specific_flavor(new_flavor_info)
    
    def take_over_new_vms(self, ptype, platform_vms_list, hostname, zone, network_id, platform_name):
        """接管异构平台上的虚拟机到openstack平台
        :param ptype: 异构平台的类型
        :param platfrom_vms_list: 异构平台的虚拟机列表
        :param hostname: 接管异构平台的主机名
        :param zone: 接管异构平台的所属域
        :param network_id: 异构平台所属的网络ID
        """
        def add_vms(platform_vm_info):  
            try:
                self._add_vm(ptype, platform_vm_info, zone, network_id, image_id, hostname)
                log.logger.info("take over new vm success, vm_id: %s, vm_name: %s" % \
                                (platform_vm_info["id"], platform_vm_info["name"]))
            except RequestError:
                vm_id = platform_vm_info["id"]
                vm_name = platform_vm_info["name"]
                log.logger.error("take over new vm failed. vm_id:%s, vm_name:%s" % (vm_id, vm_name))
                print "RequestError........."
                
        #检查是否存在有效的镜像
        image_id = self.get_image_id(ptype)
        if not image_id:
            log.logger.error("take over %s vms not found vaild images" % ptype)
            raise ImageNotFound()
        
        db_util = NovaDatabaseUtils()
        local_vm_list = db_util.get_vm_info_list(hostname)
        local_vm_map = {}
        for vm in local_vm_list:
            local_vm_map[vm["id"]] = vm
        
        #删除与要接管的虚机有相同ID的本的虚拟机
        for platform_vm_info in platform_vms_list:
            if platform_vm_info["id"] in local_vm_map.keys():
                self._delete_local_instance(ptype, local_vm_map[platform_vm_info["id"]])
            
            self._delete_instance_db(ptype, platform_vm_info["id"])
                
            #检测是否创建新的flavor
            self.check_create_new_flavor(platform_vm_info)
                
        #执行接管创建虚拟机操作
        for index, platform_vm_info in enumerate(platform_vms_list):    
#             if not self.check_is_exist_platform(platform_name):
#                 return
            
            if index != 0 and (index + 1) % 6 == 0:
                time.sleep(10)
            tContext = threading.Thread(target=add_vms, args=(platform_vm_info, ))
            tContext.start() 
        
    def check_is_exist_platform(self, platform_name):
        platformDB = PlatformDatabase(PlatformDBConfig)
        querysql = "select * from managercenterinfo where managercentername='%s';" % platform_name
        platformDB.query(querysql)
        return db_con.fetchAllRows() 
            
    def synchronism(self, ptype, platfrom_vms_list, hostname, zone, network_id, platform_name, specify_sync_vms_uuid=[]):
        '''
        与异构平台上的虚拟机进行同步
        :param ptype: 异构平台的类型
        :param platfrom_vms_list: 异构平台的虚拟机列表
        :param hostname: 接管异构平台的主机名
        :param zone: 接管异构平台的所属域
        :param network_id: 异构平台所属的网络ID
        :param specify_sync_vms_uuid: 同步指定的虚拟机id列表
        '''
        #获取所属主机名是hostname的本的虚拟机列表信息
        db_util = NovaDatabaseUtils()
        host_vms_list = db_util.get_vm_info_list(hostname)
        
        #删除列表中状态是'error'的虚拟机
        local_vm_list = []
        for host_vm in host_vms_list:
            if host_vm["vm_state"] == "error":
                self._delete_local_instance(ptype, host_vm)
                self._delete_instance_db(ptype, host_vm["id"])
            else:
                local_vm_list.append(host_vm)
        
        #如果平台类型为cserver,则进行ID的影射转换
        if ptype == "cserver":
            cserver_db = PlatformDatabase(CServerDBConfig)
            for plat_vm in platfrom_vms_list:
                sql = db.common.SELECT_CSERVER_UUID_MAP_TABLE_SQL % plat_vm["id"]
                cserver_db.query(sql)
                opestack_uuid = cserver_db.fetchOneRow()
                if opestack_uuid:
                    plat_vm["id"] = opestack_uuid[0]
                
            cserver_db.close()
        
        local_vm_uuid_list = [vm["id"] for vm in local_vm_list]
        platform_vm_uuid_list = [vm["id"] for vm in platfrom_vms_list]
    
        common_vm_map = {}
        
        #得到本地虚拟机列表和平台虚拟机列表中具有共同uuid值的虚拟机列表
        for vm_info in platfrom_vms_list:
            if vm_info["id"] in local_vm_uuid_list:
                common_vm_map[vm_info["id"]] = vm_info
                
        new_instances_list = []
        deleted_instances_list = []
        
        #获取平台中新添加的虚拟机列表
        for pvm in platfrom_vms_list:
            if pvm["id"] not in local_vm_uuid_list:
                new_instances_list.append(pvm)

        #在本的创建异构平台上新添加的虚拟机
        if new_instances_list:
            log.logger.info("synchronism new vm")
            print "add new instance................"
            self.take_over_new_vms(ptype, new_instances_list, hostname, zone, network_id, platform_name)
        
        for vm_info in local_vm_list:
            if vm_info["id"] not in platform_vm_uuid_list:
                #删除本地虚拟机(在vcenter或cserver那边已经删除的虚拟机)
                deleted_instances_list.append(vm_info["id"])
                self._delete_local_instance(ptype, vm_info)
                self._delete_instance_db(ptype, vm_info["id"])
            else:
                #同步两边具有相同uuid的虚拟机的状态
                if vm_info["id"] in common_vm_map.keys():
                    if specify_sync_vms_uuid:
                        if vm_info["id"] in specify_sync_vms_uuid:
                            self._sync_vm_state(ptype, common_vm_map[vm_info["id"]])
                    else:
                        self._sync_vm_state(ptype, common_vm_map[vm_info["id"]])
                
                    if ptype == "cserver":
                        cserver_db = PlatformDatabase(CServerDBConfig)
                        openstack_uuid = vm_info["id"]
                        vm_ip = common_vm_map[vm_info["id"]]["ip"]
                        print vm_ip, openstack_uuid
                        sql = db.common.UPDATE_CSERVER_UUID_MAP_TABLE_SQL % (vm_ip, openstack_uuid)
                        cserver_db.update(sql)
                        cserver_db.close()
                        
