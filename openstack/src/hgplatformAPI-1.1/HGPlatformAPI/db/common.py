#coding:utf-8

'''异构接管的数据库名称'''
VIRT_PLATFORM_DB = "virt_platform_db"

'''异构平台的信息表'''
MANAGER_CENTER_INFO_TABLE = "managercenterinfo"

'''cserver虚拟机的uuid影射表'''
CSERVER_INSTANCE_MAP_TABLE = "cserver_uuid_maps"

'''vcenter虚拟机的信息表'''
VCENTER_INSTANCE_MAP_TABLE = 'vcenter_uuid_maps'

'''创建表managercenterinfo的语句'''  
MANAGER_CENTER_INFO_TABLE_SQL = "create table managercenterinfo( \
                                    id int primary key auto_increment, \
                                    managercentername varchar(25) not null unique, \
                                    uuid varchar(50) not null, \
                                    virtualplatformtype varchar(30) not null, \
                                    domainname varchar(30) not null, \
                                    hostname  varchar(30) not null, \
                                    tenantname varchar(30) not null, \
                                    network_id varchar(50) not null, \
                                    virtualplatformIP varchar(30) not null, \
                                    virtualplatformusername  varchar(50) not null, \
                                    virtualplatformpassword  varchar(50) not null, \
                                    datacentersandclusters   Text );"
                     
'''创建表cserver_uuid_maps的语句'''     
CSERVER_INSTANCE_TABLE_SQL = "create table cserver_uuid_maps( \
                            id int primary key auto_increment, \
                            openstack_uuid varchar(50) not null unique, \
                            cserver_uuid varchar(50) not null unique, \
                            ip  varchar(30) not null, \
                            flavor_id varchar(50) not null);"
                            
                        
'''创建表vcenter_uuid_maps的语句'''     
VCENTER_INSTANCE_TABLE_SQL = "create table vcenter_uuid_maps( \
                            id int primary key auto_increment, \
                            openstack_uuid varchar(50) not null unique, \
                            vcenter_uuid varchar(50) not null unique, \
                            ip  varchar(30) not null, \
                            flavor_id varchar(50) not null);"

# CSERVER_INSTANCE_TABLE_SQL = "create table cserver_uuid_maps( id int primary key auto_increment, openstack_uuid varchar(50) not null unique, cserver_uuid varchar(50) not null unique, );"
'''判断数据库是否存在的sql语句'''
CHECK_DB_EXIST_SQL = "SELECT * FROM information_schema.SCHEMATA where SCHEMA_NAME='%s';"


'''判断表是否存在的sql语句'''
CHECK_TABLE_EXIST_SQL = "select `TABLE_NAME` from `INFORMATION_SCHEMA`.`TABLES` \
                                  where `TABLE_SCHEMA`='%s' and `TABLE_NAME`='%s';"
                                  

'''插入表managercenterinfo的sql语句'''                          
INSERT_MANAGER_CENTER_INFO_TABLE_SQL = "insert into managercenterinfo (managercentername, uuid, \
                                        virtualplatformtype, domainname, hostname, tenantname, \
                                        network_id, virtualplatformIP, virtualplatformusername, \
                                        virtualplatformpassword, datacentersandclusters) \
                                        values('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s');"
             
'''插入表cserver_uuid_maps的sql语句'''
INSERT_CSERVER_UUID_MAP_TABLE_SQL = "insert into cserver_uuid_maps (openstack_uuid, cserver_uuid, ip, flavor_id) values('%s', '%s', '%s', '%s');"
             
'''删除表数据的sql语句'''
DELETE_CSERVER_UUID_MAP_TABLE_SQL = "delete from cserver_uuid_maps where openstack_uuid='%s';"

'''选择表数据的sql语句'''
SELECT_CSERVER_UUID_MAP_TABLE_SQL = "select openstack_uuid from cserver_uuid_maps where cserver_uuid='%s';"
             
'''更新表数据的sql语句'''
UPDATE_CSERVER_UUID_MAP_TABLE_SQL = "update cserver_uuid_maps set ip='%s' where openstack_uuid='%s';"
     
    
'''插入表vcenter_uuid_maps的sql语句'''
INSERT_VCENTER_UUID_MAP_TABLE_SQL = "insert into vcenter_uuid_maps (openstack_uuid, vcenter_uuid, ip, flavor_id) values('%s', '%s', '%s', '%s');"

'''删除表数据的sql语句'''
DELETE_VCENTER_UUID_MAP_TABLE_SQL = "delete from vcenter_uuid_maps where openstack_uuid='%s';"

'''选择表数据的sql语句'''
SELECT_VCENTER_UUID_MAP_TABLE_SQL = "select openstack_uuid from vcenter_uuid_maps where vcenter_uuid='%s';"
             
'''更新表数据的sql语句'''
UPDATE_CSERVER_UUID_MAP_TABLE_SQL = "update vcenter_uuid_maps set ip='%s' where openstack_uuid='%s';"
     

MYSQL_USER = "root"
MYSQL_PORT = 3306
MYSQL_HOST = 'localhost'
MYSQL_CHARSET = 'utf8'


'''平台的数据库配置'''
PlatformDBConfig = {'host': MYSQL_HOST, 
            'port': MYSQL_PORT, 
            'user': MYSQL_USER, 
            'db': VIRT_PLATFORM_DB,
            'table': MANAGER_CENTER_INFO_TABLE,
            'createsql': MANAGER_CENTER_INFO_TABLE_SQL, 
            'charset': MYSQL_CHARSET}
             
             
'''cserver平台的数据库配置'''
CServerDBConfig = {'host': MYSQL_HOST, 
            'port': MYSQL_PORT, 
            'user': MYSQL_USER, 
            'db': VIRT_PLATFORM_DB,
            'table': CSERVER_INSTANCE_MAP_TABLE,
            'createsql': CSERVER_INSTANCE_TABLE_SQL, 
            'charset': MYSQL_CHARSET}
             
'''cserver平台的数据库配置'''
VCenterDBConfig = {'host': MYSQL_HOST, 
            'port': MYSQL_PORT, 
            'user': MYSQL_USER, 
            'db': VIRT_PLATFORM_DB,
            'table': VCENTER_INSTANCE_MAP_TABLE,
            'createsql': VCENTER_INSTANCE_TABLE_SQL, 
            'charset': MYSQL_CHARSET}
             
'''nova数据库的配置'''
NovaDBConfig = {'host': MYSQL_HOST, 
            'port': MYSQL_PORT, 
            'user': MYSQL_USER, 
            'db': 'nova',
            'table': 'instances',
            'charset': MYSQL_CHARSET}
             
             
             
