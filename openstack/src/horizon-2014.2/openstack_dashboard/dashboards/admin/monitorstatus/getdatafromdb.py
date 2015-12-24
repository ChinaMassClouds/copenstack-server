#/usr/bin/python

import pymongo

class MonitoInfoQuery(object):

     def __init__(self,host_ip,port=27017):
      
       try:
          self._conn = pymongo.Connection(host_ip,port)
          self._collect = self._conn.ceilometer.meter
       except Exception,e:
          print e


     def query(self,query,filte=None,limit=0,sort=0):
         if   limit == 0 and sort == 0:
             return self._collect.find(query,filte)
         elif limit == 0 and sort != 0:
                return self._collect.find(query,filte).sort([("timestamp",sort)])
         elif limit !=0 and sort ==0:
                return self._collect.find(query,filte).limit(limit)
         elif limit !=0 and sort !=0:
                return self._collect.find(query,filte).sort([("timestamp",sort)]).limit(limit)

     def getSampleDatas(self,resource_id,counter_name,sort=0,limit=0):
         resource = []
         query ={"resource_id":{"$regex":resource_id},"counter_name":counter_name}

         filte ={"_id":0,"counter_volume":1,"timestamp":1,"counter_unit":1}
         result = self.query(query,filte,limit,sort)
         unit = ''
         for data in result:
             dic = {'x':data.get('timestamp').strftime("%Y-%m-%dT%H:%M:%S"),
                    'y':data.get('counter_volume')}

             unit = data.get('counter_unit')
             resource.append(dic)
         
         my_dic = {}
         for r in resource:
             if my_dic.get(r.get('x')):
                 my_dic[r.get('x')] += r.get('y')
             else:
                 my_dic[r.get('x')] = r.get('y')
         my_list = []
         for k in my_dic.keys():
             my_list.append({'x':k,'y':my_dic.get(k)})
         my_list.sort(key = lambda i : i.get('x'))

         return (my_list,unit)
