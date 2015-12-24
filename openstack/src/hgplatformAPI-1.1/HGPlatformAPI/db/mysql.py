#coding:utf-8
import MySQLdb
import common
from utils import com_utils

class DB(object):
    '''对MySQLdb常用函数进行封装的类'''
    _instance = None #本类的实例
    _conn = None # 数据库conn
    _cur = None #游标
    
    def __init__(self, dbconfig):
        '''构造器：根据数据库连接参数，创建MySQL连接,创建相应数据库和表'''
        self._conn = self.get_connection(dbconfig)
        self._cur = self._conn.cursor()

    def get_connection(self, dbconfig):
        '''根据参数获取数据库的连接'''
        mysql_passwd = com_utils.get_mysql_password()
        return MySQLdb.connect(host=dbconfig['host'],
                         port=dbconfig['port'],
                         db=dbconfig['db'], 
                         user=dbconfig['user'],
                         passwd=mysql_passwd,
                         charset=dbconfig['charset'])
        
    def query(self,sql):
        '''执行 SELECT 语句'''
        self._cur.execute("SET NAMES utf8") 
        result = self._cur.execute(sql)
        return result

    def delete(self, sql):
        '''执行 DELETE 语句'''
#         try:
        self._cur.execute("SET NAMES utf8") 
        self._cur.execute(sql)
        self._conn.commit()
#         except MySQLdb.Error, e:
#             self.error_code = e.args[0]
#             print "数据库错误代码:",e.args[0],e.args[1]
#             result = False
        
    def update(self,sql):
        '''执行 UPDATE 语句'''
        self._cur.execute("SET NAMES utf8") 
        self._cur.execute(sql)
        self._conn.commit()

    
    def insert(self,sql):
        '''执行 INSERT 语句。如主键为自增长int，则返回新生成的ID'''
        self._cur.execute("SET NAMES utf8")
        self._cur.execute(sql)
        self._conn.commit()
        return self._conn.insert_id()
  
    def fetchAllRows(self):
        '''返回结果列表'''
        return self._cur.fetchall()

    def fetchOneRow(self):
        '''返回一行结果，然后游标指向下一行。到达最后一行以后，返回None'''
        return self._cur.fetchone()
 
    def getRowCount(self):
        '''获取结果行数'''
        return self._cur.rowcount
              
    def commit(self):
        '''数据库commit操作'''
        self._conn.commit()
                
    def rollback(self):
        '''数据库回滚操作'''
        self._conn.rollback()
           
    def __del__(self): 
        '''释放资源（系统GC自动调用）'''
        try:
            self._cur.close() 
            self._conn.close() 
        except:
            pass
        
    def close(self):
        '''关闭数据库连接'''
        self.__del__()

class NovaDatabase(DB):
    
    def __init__(self, dbconfig):
        DB.__init__(self, dbconfig)
    
    def get_connection(self, dbconfig):
        '''根据参数获取数据库的连接'''
        mysql_host_ip = com_utils.get_mysql_address()
        mysql_passwd = com_utils.get_mysql_password()
        local_ip = com_utils.get_local_ip()
             
        if mysql_host_ip and local_ip and (mysql_host_ip == local_ip):
            return MySQLdb.connect(host=dbconfig['host'],
                         port=dbconfig['port'], 
                         user=dbconfig['user'],
                         db=dbconfig['db'],
                         charset=dbconfig['charset'])
        else:
            return MySQLdb.connect(host=mysql_host_ip,
                         port=dbconfig['port'],
                         db=dbconfig['db'], 
                         user=dbconfig['user'],
                         passwd=mysql_passwd,
                         charset=dbconfig['charset'])



class PlatformDatabase(DB):
        
    def __init__(self, dbconfig):
        DB.__init__(self, dbconfig)
        self.create_db(dbconfig['db'])
        self._conn.select_db(dbconfig['db'])
        self.create_table(dbconfig['db'], dbconfig['table'], dbconfig['createsql'])
    
    def get_connection(self, dbconfig):
        '''根据参数获取数据库的连接'''
        mysql_host_ip = com_utils.get_mysql_address()
        mysql_passwd = com_utils.get_mysql_password()
        local_ip = com_utils.get_local_ip()
             
        if mysql_host_ip and local_ip and (mysql_host_ip == local_ip):
            return MySQLdb.connect(host=dbconfig['host'],
                         port=dbconfig['port'], 
                         user=dbconfig['user'],
                         charset=dbconfig['charset'])
        else:
            return MySQLdb.connect(host=mysql_host_ip,
                         port=dbconfig['port'], 
                         user=dbconfig['user'],
                         passwd=mysql_passwd,
                         charset=dbconfig['charset'])
            
    def create_db(self, db):
        '''创建数据库'''
        if not self._cur.execute(common.CHECK_DB_EXIST_SQL % db):
            self._cur.execute("create database %s" % db)
    
    def create_table(self, db, table, createsql):
        '''创建表'''
        if not self._cur.execute(common.CHECK_TABLE_EXIST_SQL % (db, table)):
            print "createsql:", createsql
            self._cur.execute(createsql)
            
