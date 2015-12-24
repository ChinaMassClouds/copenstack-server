#/usr/bin/python
#coding:utf-8

import pymongo
import sys
from datetime import  timedelta
import datetime

class Top(object):
     def __init__(self,host_ip,port=27017):
       try:
          self._conn = pymongo.Connection(host_ip,port)
          print self._conn
          self ._collect = None
       except Exception,e:
          print e

     def setCollection(self,db_name,collection):
         try:
            self._collect =self._conn[db_name][collection]
         except Exception , e:
            print e

     def query_resource_id(self):
         if self._collect is not None:
           return  self._collect.distinct("resource_id")
         return None

     def query_field_new_value(self,timestamp,resource_type):

         if self._collect is not None:
           ids = []
           cluster =  self._collect.find({"counter_name":resource_type,"timestamp":{"$gt":timestamp}},{"_id":0,"counter_volume":1,"resource_id":1}).sort("counter_volume",-1)  
           if cluster is not None:
              for value in cluster :
                  ids.append(value)
           return ids

     def top(self,resource_type):
          ids_copy=[]
          timestamp = datetime.datetime.today() - datetime.timedelta(minutes=30)
          ids = self.query_field_new_value(timestamp,resource_type)
          if len(ids) == 0:
             return ids_copy
          for Value in ids:
              if Value["resource_id"] != u'':
                 ids_copy.append(Value)
                 break
              ids.remove(Value)

          index = 0
          while index < len(ids):
                falg = True
                for value in ids_copy:
                    if ids[index]["resource_id"] == u'' or ids[index]["resource_id"] == value["resource_id"]:
                         falg = False
                         break
                if falg:
                         ids_copy.append(ids[index])
                if len(ids_copy) == 5:
                     ids_copy.sort(lambda x,y:cmp(x["counter_volume"],y["counter_volume"]),reverse=True)
                     return ids_copy
                index +=1
          ids_copy.sort(lambda x,y:cmp(x["counter_volume"],y["counter_volume"]),reverse=True)
          return ids_copy
