#coding:utf-8

#异构接管的数据库名称
VIRT_PLATFORM_DB = "virt_platform_db"

#cserver虚拟机的uuid影射表
CSERVER_INSTANCE_MAP_TABLE = "cserver_uuid_maps"

#创建表的语句
CSERVER_INSTANCE_TABLE_SQL = "create table cserver_uuid_maps( \
                                    id int primary key auto_increment, \
                                    openstack_uuid varchar(50) not null unique, \
                                    cserver_uuid varchar(50) not null unique, \
                                    ip varchar(30) not null, \
                                    flavor_id varchar(50) not null, \
                                    );"

#判断数据库是否存在的sql语句
CHECK_DB_EXIST_SQL = "SELECT * FROM information_schema.SCHEMATA where SCHEMA_NAME='%s';"

#判断表是否存在的sql语句
CHECK_TABLE_EXIST_SQL = "select `TABLE_NAME` from `INFORMATION_SCHEMA`.`TABLES` \
                                  where `TABLE_SCHEMA`='%s' and `TABLE_NAME`='%s';"
             
#插入表数据的sql语句
INSERT_CSERVER_UUID_MAP_TABLE_SQL = "insert into cserver_uuid_maps (openstack_uuid, cserver_uuid, ip, flavor_id) values('%s', '%s', '%s', '%s');"

#删除表数据的sql语句         
DELETE_CSERVER_UUID_MAP_TABLE_SQL = "delete from cserver_uuid_maps where openstack_uuid='%s';"
    
#选择表数据的sql语句         
SELECT_CSERVER_UUID_MAP_TABLE_SQL = "select cserver_uuid from cserver_uuid_maps where openstack_uuid='%s';"
    
#更新表数据的sql语句
UPDATE_CSERVER_UUID_MAP_TABLE_SQL = "update cserver_uuid_maps set ip='%s' where openstack_uuid='%s';"
         
MYSQL_USER = "root"
MYSQL_PORT = 3306
MYSQL_HOST = 'localhost'
MYSQL_CHARSET = 'utf8'

             
CServerDBConfig = {'host': MYSQL_HOST, 
            'port': MYSQL_PORT, 
            'user': MYSQL_USER, 
            'db': VIRT_PLATFORM_DB,
            'table': CSERVER_INSTANCE_MAP_TABLE,
            'createsql': CSERVER_INSTANCE_TABLE_SQL, 
            'charset': MYSQL_CHARSET}
             

#########控制虚拟机的操作###########
CSERVER_VM_START = "start"
CSERVER_VM_SHUTDOWN = "shutdown"
CSERVER_VM_REBOOT = "reboot"
CSERVER_VM_STOP = "stop"  #断电 
                     
#########虚拟机的电源状态############       
UNKNOWN = 'unknown'
RUNNING = 'up'
PAUSED = 'paused'
SHUTDOWN = 'down'
SUSPENDED = 'suspended'
                     
CSERVER_POWER_STATE = {
                       UNKNOWN: 0,
                       RUNNING: 1,
                       SHUTDOWN: 4,
                       SUSPENDED: 7,
                       }         
 