#coding:utf-8


from db.mysql import NovaDatabase
from db.common import NovaDBConfig

class NovaDatabaseUtils(object):
    """
    nova数据库操作类
    """
    _instance = None
    
    def __init__(self, dbconfig=NovaDBConfig):
        self._CSever_list = []
        super(NovaDatabaseUtils, self).__init__()
        self._db = NovaDatabase(dbconfig)
        
    def get_vm_info_list(self, host_name):
        """根据主机名，获取该主机下的虚拟机信息"""
        local_vm_info_list = []
        sql = "select uuid, display_name, power_state, memory_mb, vcpus, user_id, vm_state from instances where host='%s' and vm_state!='deleted';" % host_name
        self._db.query(sql)
        db_content = self._db.fetchAllRows()
        
        for item in db_content:
            vm_info_map = {}
            vm_info_map["id"] = item[0]
            vm_info_map["name"] = item[1]
            vm_info_map["power_state"] = item[2]
            vm_info_map["ram"] = item[3]
            vm_info_map["vcpus"] = item[4]
            vm_info_map["user_id"] = item[5]
            vm_info_map["vm_state"] = item[6]
            local_vm_info_list.append(vm_info_map)
        
        return local_vm_info_list
    
    
    def update_vm_info(self, sql):
        """更新一条虚拟机的记录"""
        self._db.update(sql)
    
    
    def query_vm_state(self, vm_id):
        """根据虚拟机的id，查询该虚拟机的状态"""
        sql = "select vm_state from instances where uuid='%s';" % vm_id
        self._db.query(sql)
        return self._db.fetchOneRow()
    
    def query_resource_usage(self, tenant_id, user_id):
        """
        根据tennat的id信息，查询该租户下的资源使用情况
        实例instance
        内存ram
        虚拟机内核cores
        """
        instance_usage = -1
        ram_usage = -1
        cores_usage = -1
        sql = "select in_use from quota_usages where project_id='%s' and resource='instances' and user_id='%s';" % \
                    (tenant_id, user_id)
        self._db.query(sql)
        instance_data = self._db.fetchOneRow()
        if instance_data:
            instance_usage = int(instance_data[0])
        
        sql = "select in_use from quota_usages where project_id='%s' and resource='ram' and user_id='%s';" % \
                    (tenant_id, user_id)
        self._db.query(sql)
        ram_data = self._db.fetchOneRow()
        if ram_data:
            ram_usage = int(ram_data[0])
        
        sql = "select in_use from quota_usages where project_id='%s' and resource='cores' and user_id='%s';" % \
                    (tenant_id, user_id)
        self._db.query(sql)
        core_data = self._db.fetchOneRow()
        if core_data:
            cores_usage = int(core_data[0])
        
        print instance_usage, ram_usage, cores_usage
        
        return instance_usage, ram_usage, cores_usage
    
    def update_resource_usage(self, tenant_id, user_id, instance_usage, ram_usage, cores_usage):
        """更新该租户下的资源使用情况"""
        
        update_instance_sql = "update quota_usages set in_use=%s where project_id='%s' and resource='instances' and user_id='%s';" \
                              % (instance_usage, tenant_id, user_id)
        update_ram_sql = "update quota_usages set in_use=%s where project_id='%s' and resource='ram' and user_id='%s';" \
                              % (ram_usage, tenant_id, user_id)
        update_cores_sql = "update quota_usages set in_use=%s where project_id='%s' and resource='cores' and user_id='%s';" \
                              % (cores_usage, tenant_id, user_id)
        
        self._db.update(update_instance_sql)
        self._db.update(update_ram_sql)
        self._db.update(update_cores_sql)
    
