#coding:utf-8

from exception import NoveComputeServiceFailed, SSHLoginFailed
import paramiko, json, uuid
from db import common
from db.mysql import PlatformDatabase
from db.common import PlatformDBConfig
from tools.takeovertool import VMTakeoverTools
from utils import com_utils
from db.mysql import NovaDatabase
from db.common import NovaDBConfig
from db.novdb_utils import NovaDatabaseUtils
from logrecord import log


class PlatformManager(object):
    """
    平台管理基础类
    """
    _ptype = ""
    _sync_user = "syncadmin"
    _sync_user_password = "root+-*/root"
    _tenant_name = "admin"
    def __init__(self):
        self._dbconncet = None
        self._platform_obj_list = []
        
    
    def _get_platform_info_obj_list(self):
        """
        获取平台实例信息对象的列表
        """
        if not self._platform_obj_list:
            self.get_platform_instances_info()
        return self._platform_obj_list
    
    def get_specify_platform_instance_info(self, platform_uuid):
        """获取指定平台的信息
        :param platform_uuid: 平台的uuid信息
        """
        platform_info = {}
        for vcobj in self._get_platform_info_obj_list():
            if vcobj.uuid == platform_uuid:
                platform_info["name"] = vcobj.name
                platform_info["uuid"] = vcobj.uuid
                platform_info["domain_name"] = vcobj.domain_name
                platform_info["dc_cluster"] = vcobj.dc_cluster
                platform_info["hostname"] = vcobj.hostname
                platform_info["virtualplatformtype"] = vcobj.virtualplatformtype
                platform_info["virtualplatformIP"] = vcobj.virtualplatformIP
                platform_info["virtualplatformusername"] = vcobj.virtualplatformusername
                platform_info["virtualplatformpassword"] = vcobj.virtualplatformpassword
                
#         print "specity platform_info:", platform_info 
        return platform_info
    
    def auto_synchronism(self):
        """自动同步异构平台上的虚拟机"""
        self.update_platform_dc_cluster()
        platform_instance_info_list = self.get_platform_instances_info()
        for platform_instance in platform_instance_info_list:
            self._synchronism(platform_instance)
        
    def update_platform_dc_cluster(self):
        for platform_instance in self._get_platform_info_obj_list():
            dc_cluster = platform_instance.get_platform_base_info()
            if dc_cluster:
                new_dc_cluster = json.dumps(dc_cluster)
                uuid = platform_instance.uuid
                updatesql = "update managercenterinfo set datacentersandclusters='%s' where uuid='%s';" % (new_dc_cluster, uuid)
                self._update_db(updatesql)
        
    def query_platform_instances(self):
        """从数据库中查询异构平台的信息"""
        platform_instance_info_list = []
        querysql = "select * from managercenterinfo where virtualplatformtype='%s';" % self._ptype
        for platform in self._query_db(querysql):
            instance_info = {}
            instance_info["name"] = platform[1]
            instance_info["uuid"] = platform[2]
            instance_info["virtualplatformtype"] = platform[3]
            instance_info["domain_name"] = platform[4]
            instance_info["hostname"] = platform[5]
            instance_info["tenantname"] = platform[6]
            instance_info["network_id"] = platform[7]
            instance_info["virtualplatformIP"] = platform[8]
            instance_info["virtualplatformusername"] = platform[9]
            instance_info["virtualplatformpassword"] = platform[10]
            dc_and_cluster = json.loads(str(platform[11]))
            instance_info["datacentersandclusters"] = dc_and_cluster
            instance_info["datacenternum"] = len(dc_and_cluster.keys())
            cluster_num = 0
            for dc in dc_and_cluster.keys():
                cluster_num += len(dc_and_cluster[dc])
            instance_info["clusternum"] = cluster_num 
            
            platform_instance_info_list.append(instance_info)
        return platform_instance_info_list
    
    def get_platform_instances_info(self):
        """获取平台实例信息及状态信息"""
        self.clear()
        platform_instance_info_list = self.query_platform_instances()
        for platform_instance in platform_instance_info_list:
            try:
                self._platform_obj_list.append(self.create_platform_info_obj(platform_instance))
                platform_instance['status'] = 'enabled'
            except Exception:
                print "create error.........."
                platform_instance['status'] = 'failed'
            
        return platform_instance_info_list
      
    def create_platform_info_obj(self):
        pass
    
    def _synchronism(self, instance_info):
        """同步异构平台上的虚拟机到本的平台"""
        instance_info["username"] = self._sync_user
        instance_info["passwd"] = self._sync_user_password
        info_obj = self.create_platform_info_obj(instance_info)

        specity_vm_uuid_list = instance_info.get("vm_uuid_list", [])
        cn_address = com_utils.get_controller_node_address()
        platform_vm_info_list = info_obj.get_vms_info()
        
        if platform_vm_info_list:
            tool = VMTakeoverTools(cn_address, instance_info["tenantname"], \
                                    instance_info["username"], instance_info["passwd"], \
                                    )
            tool.synchronism(self._ptype, platform_vm_info_list, instance_info["hostname"], \
                                    instance_info["domain_name"], instance_info["network_id"], \
                                    instance_info["name"], specity_vm_uuid_list)
         
    
    def _add_platform_instance(self, instance_info, cmd_list, reset_cmd_list):
        """
        添加vcenter平台实例
        _@instance_info:平台实例的基础信息,集群的用户名，密码和地址信息，接管集群等
        """
        instance_info["uuid"] = str(uuid.uuid4())
        info_obj = self.create_platform_info_obj(instance_info)

        cn_address = com_utils.get_controller_node_address()
        platform_vm_info_list = info_obj.get_vms_info()
        
        print "platform_vm_info_list:", platform_vm_info_list
        
        self._exec_remote_cmd(instance_info["hostname"], cmd_list, reset_cmd_list)
        self._platform_obj_list.append(info_obj)
          
        if platform_vm_info_list:
            tool = VMTakeoverTools(cn_address, instance_info["tenantname"], \
                                    instance_info["username"], instance_info["passwd"], \
                                    )
            tool.take_over_new_vms(self._ptype, platform_vm_info_list, \
                                   instance_info["hostname"], instance_info["domain_name"], \
                                   instance_info["network_id"], instance_info["name"])
             
        self._insert_db(instance_info)

    def _remove_platform_instance(self, instance_info, cmd_list):
        """
        删除vcenter平台实例
        _@instance_info:平台实例的基础信息,集群的用户名，密码和地址信息，接管集群等
        """
        cn_address = com_utils.get_controller_node_address()
        tool = VMTakeoverTools(cn_address, instance_info["tenantname"], \
                                    instance_info["username"], instance_info["passwd"])
        tool.delete_platform_instances(self._ptype, instance_info["hostname"])
        
        deletesql = "delete from managercenterinfo where uuid='%s'" % instance_info["uuid"]
        self._remove_from_db(deletesql)
    
        for vc_instance in self._platform_obj_list:
            if vc_instance._uuid == instance_info["uuid"]:
                self._platform_obj_list.remove(vc_instance)
                break
            
        self._exec_remote_cmd(instance_info["hostname"], cmd_list)

    def _get_db_conncet(self):
        """
        获取数据库的链接
        """
        if not self._dbconncet:
            self._dbconncet = PlatformDatabase(PlatformDBConfig)
            
        return self._dbconncet
    
    def _insert_db(self, instance_info):
        """
        向数据库中添加记录
        """
        db_con = self._get_db_conncet()
        db_con.insert(common.INSERT_MANAGER_CENTER_INFO_TABLE_SQL % (instance_info["name"], \
                            instance_info["uuid"], instance_info["virtualplatformtype"], instance_info["domain_name"], \
                            instance_info["hostname"], instance_info["tenantname"], instance_info["network_id"], \
                            instance_info["virtualplatformIP"], instance_info["virtualplatformusername"], \
                            instance_info["virtualplatformpassword"], json.dumps(instance_info["datacentersandclusters"])))

    def _query_db(self, querysql, fetchAll=True):
        """查询数据库的信息"""
        db_con = self._get_db_conncet()
        db_con.query(querysql)
        if fetchAll:
            return db_con.fetchAllRows() 
        return db_con.fetchOneRow()
        
    def _remove_from_db(self, deletesql):
        """删除数据库的记录"""
        db_con = self._get_db_conncet()
        db_con.delete(deletesql)
        
    def _update_db(self, updatesql):
        db_con = self._get_db_conncet()
        db_con.update(updatesql)
        
    def _exec_remote_cmd(self, address, cmd_list, reset_cmd_list=[], username="root", password="rootroot"):
        """
        对远程的主机进行操作
        _@address: 远程主机的地址
        _@cmd_list: 需要在远程主机上执行的命令
        _@username： 远程主机用户名
        _@password： 远程主机秘密
        """
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(address, 22, username, password)
        except Exception:
            SSHLoginFailed(address)
            
        output = []
        for cmd in cmd_list:
            stdin, stdout, stderr = ssh.exec_command(cmd)
            output = stdout.readlines()
#             print "cmd:", cmd
            
#         print "output:", output
        if not output or output[0] == u"compute service failed\n":
            log.logger.info("Config plateform %s openstack-nova-compute service failed" % self._ptype)
            for reset_cmd in reset_cmd_list:
#                 print "reset_cmd:", reset_cmd
                ssh.exec_command(reset_cmd)
            ssh.close()
            raise NoveComputeServiceFailed()
        
        log.logger.info("Config plateform %s openstack-nova-compute service success" % self._ptype)
        ssh.close()
        
    def get_datacenter_info_list(self):
        """
        获取数据中心的信息列表
        """
        dc_info = []
        for vcobj in self._get_platform_info_obj_list():
            for info in vcobj.get_dc_info():
                dc_info.append(info)
        print dc_info
        return dc_info
    
    def get_cluster_info_list(self):
        """
        获取集群的信息列表
        """
        cluster_info = []
        for vcobj in self._get_platform_info_obj_list():
            for info in vcobj.get_dc_cluster_info():
                cluster_info.append(info)
        print cluster_info
        return cluster_info
    
    def get_host_info(self):
        """
        获取主机的信息列表
        """
        host_info = []
        for vcobj in self._get_platform_info_obj_list():
            for info in vcobj.get_dc_cluster_host_info():
                host_info.append(info)
        print host_info
        return host_info
    
    def get_template_list(self, platfrom_name):
        """获取模板列表信息"""
        for vcobj in self._get_platform_info_obj_list():
            if vcobj.name == platfrom_name:
                cn_address = com_utils.get_controller_node_address()
                tool = VMTakeoverTools(cn_address, self._tenant_name, \
                                    self._sync_user, self._sync_user_password, \
                                    )
                template_list = vcobj.get_template_list()
                for template in template_list:
                    tool.check_create_new_flavor(template)
                    
                return template_list
        return []
    
    def get_vm_info_list(self, platfrom_name):
        for vcobj in self._get_platform_info_obj_list():
            if vcobj.name == platfrom_name:
                return vcobj.get_vms_info()
        return []
    
    def get_platform_base_info(self, instance_info):
        """
        获取异构平台的数据中心集群基础信息
        
        _@instance_info:平台实例的基础信息,集群的用户名，密码和地址信息等
        _@return: 例： {
                     'datacenter1':['cluster-1', 'cluster-2',], 
                     'datacenter2':['cluster-3', 'cluster-4'], 
                    }
        """
        vc_obj = self.create_platform_info_obj(instance_info)
        base_info = vc_obj.get_platform_base_info()
        print base_info
        return base_info
    
    def __del__(self): 
        del self._dbconncet
        del self._platform_obj_list[:]
       
    def clear(self):
        del self._platform_obj_list[:]
