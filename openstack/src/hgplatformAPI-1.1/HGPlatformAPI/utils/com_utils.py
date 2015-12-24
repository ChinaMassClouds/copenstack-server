#coding:utf-8
import commands

def get_mysql_address():
    """获取mysql数据库的地址"""
    mysql_host_ip = ""
    mysqloutput = commands.getstatusoutput("grep MARIADB_NODE_IP /etc/openstack.cfg | awk -F '=' '{printf $2}'")
    if mysqloutput[0] == 0:
        mysql_host_ip = str(mysqloutput[1].strip())
    return mysql_host_ip

def get_controller_node_address():
    """获取控制节点的地址"""
    controller_host_ip = ""
    controlleroutput = commands.getstatusoutput("grep CONTROLLER_NODE_IP /etc/openstack.cfg | awk -F '=' '{printf $2}'")
    if controlleroutput[0] == 0:
        controller_host_ip = str(controlleroutput[1].strip())
    return controller_host_ip

def get_local_ip():
    """得到本地的ip地址"""
    local_ip = ""
    local_ip_output = commands.getstatusoutput("source /etc/openstack.cfg && facter | grep ipaddress_$MANAGE_NETWORKCARD_NAME | awk '{print $3}'")
    if local_ip_output[0] == 0:
        local_ip = str(local_ip_output[1].strip())
    return local_ip

def get_mysql_password():
    """获取mysql数据库的密码"""
    mysql_passwd = ""
    mysqloutput = commands.getstatusoutput("grep MARIADB_USER_PASS /etc/openstack.cfg | awk -F '=' '{printf $2}'")
    if mysqloutput[0] == 0:
        mysql_passwd = str(mysqloutput[1].strip())
    return mysql_passwd

def get_mongodb_ip():
    """获取mongodb数据库的ip地址"""
    mongodb_ip = ""
    mongodb_ip_output = commands.getstatusoutput("grep MONGODB_DATABASE_IP /etc/openstack.cfg | awk -F '=' '{printf $2}'")
    if mongodb_ip_output[0] == 0:
        mongodb_ip = str(mongodb_ip_output[1].strip())
    return mongodb_ip
    
def get_user_id(user_name):
    user_id = ""
    user_id_output = commands.getstatusoutput("source /root/creds && keystone user-list | grep %s | awk '{print $2}'" % user_name)
    if user_id_output[0] == 0:
        user_id = str(user_id_output[1].strip())
    return user_id
    
def get_tenant_id(tenant_name):
    tenant_id = ""
    tenant_id_output = commands.getstatusoutput("source /root/creds && keystone tenant-list | grep %s | awk '{print $2}'" % tenant_name)
    if tenant_id_output[0] == 0:
        tenant_id = str(tenant_id_output[1].strip())
    return tenant_id
    
def convert_kb_to_g(kb_value):
    """转换单位kb为g"""
    divisor = 1024.0*1024.0*1024.0
    result = kb_value/divisor
    value = '%.2fG' % result
    return value

