# -*- coding: utf-8 -*-

import requests
import json
import commands
from ceilometer.openstack.common import log

LOG = log.getLogger(__name__)

class HttpRequests(object):
    _instance = 0
    def __init__(self, host, username, password):
        super(HttpRequests,self).__init__()
        self._host = host
        self._username = username
        self._password = password
        self._headers = {
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
        
        

    def getAuthToken(self, tenantName):
        """
        获取认证
        """
        #userInfo = LoginUserInfo.instance().getUserInfo()
        urlPath = "http://" + self._host + ":5000/v2.0/tokens"
        payload = {
                    "auth": {
                        "tenantName": tenantName,
                        "passwordCredentials": {
                            "username": self._username,
                            "password": self._password,
                                                                }
                                    }
                        }
        
        try:
            r = requests.post(urlPath, data=json.dumps(payload), headers=self._headers)
            if r.ok:
                self.currentTenantName = tenantName
                infoDict = r.json()
                self.setOpenstackServiceHost(infoDict)
                print "token:", infoDict["access"]["token"]["id"]
                self._headers.update({'X-Auth-Token': infoDict["access"]["token"]["id"]})
                return infoDict
        except requests.exceptions.ConnectionError, e:
                return "ConnectionError"
        
        return None


    def getRequestInfo(self, url, tenantName):
        """
        获取请求的信息
        @url 请求的url信息
        """
        #try:
        if not self.currentTenantName or self.currentTenantName != tenantName:
            value = self.getAuthToken(tenantName)
            if value is None or value == "ConnectionError":
                return value
            request = requests.get(url, headers=self._headers)
        else:        
            newUrl = self.getServiceURL(url)
            request = requests.get(newUrl, headers=self._headers)
            if not request.ok and request.content == authFailMsg:
                value = self.getAuthToken(tenantName)
                if value is None or value == "ConnectionError":
                    return value
                    
                request = requests.get(self.getServiceURL(url), headers=self._headers)
                    
        if request.ok:
            return request.json()
        elif request.status_code == 403:
            return "forbidden"
        else:
            return None
        
        #except requests.exceptions.ConnectionError, e:
         #       return None
        
        #return None
        
    def postRequestInfo(self, url, info, tenantName, isNeedReturnValue=False):
        """
        执行相应的请求操作
        @url 请求的url信息，
        @info 执行操作时需要的数据
        @isNeedReturnValue 执行完操作时，是否需要返回相应的信息
        """
        try:
            if not self.currentTenantName or self.currentTenantName != tenantName:
                value = self.getAuthToken(tenantName)
                if value is None or value == "ConnectionError":
                    return value
                
                request = requests.post(url, data=json.dumps(info), headers=self._headers)
            else:
                request = requests.post(url, data=json.dumps(info), headers=self._headers)
                if not request.ok and request.content == authFailMsg:
                    value = self.getAuthToken(tenantName)
                    if value is None or value == "ConnectionError":
                        return value
                    
                    request = requests.post(self.url, data=json.dumps(info), headers=self._headers)
            
            if request.status_code == 403:
                return "forbidden"
                
            if request.ok and isNeedReturnValue:
                return request.json()
            
            if request.ok and not isNeedReturnValue:
                return True
        except requests.exceptions.ConnectionError, e:
                return False
            
        print request.content
        return False
            
def get_controller_node_address():
    """获取控制节点的地址"""
    controller_host_ip = ""
    controlleroutput = commands.getstatusoutput("grep CONTROLLER_NODE_IP /etc/openstack.cfg | awk -F '=' '{printf $2}'")
    if controlleroutput[0] == 0:
        controller_host_ip = str(controlleroutput[1].strip())
    return controller_host_ip

def get_alarm_info(alarm_id):
    host_ip = get_controller_node_address()
    username = "syncadmin"
    password = "root+-*/root"
    tenantname = "admin"
    request = HttpRequests(host_ip, username, password)
    url = "http://%s:8777/v2/alarms" % host_ip
    requestInfo = request.getRequestInfo(url, tenantname)
    #LOG.info("request info: %s" % requestInfo)
    alarm_info = {}

    for ainfo in requestInfo:
        LOG.info("ainfo.id: %s, alarm_id: %s" % (ainfo["alarm_id"], alarm_id))
        if ainfo["alarm_id"] == alarm_id:
            alarm_info = ainfo
            break

    return alarm_info

def is_need_send_email(alarm_info):
    if isinstance(alarm_info["description"], dict):
        return alarm_info["description"]["mail_alarm"]
    return True


def get_alarm_condition_info(alarm_info):
    compare_mark_map = {"lt": "<", "le": "<=", "eq": "==", "ne": "!=", "ge": ">=", "gt": ">"}
    alarm_meter_name = alarm_info["threshold_rule"]["meter_name"]
    comparison_operator = compare_mark_map.get(alarm_info["threshold_rule"]["comparison_operator"], "unknown")
    threshold = alarm_info["threshold_rule"]["threshold"]
    period = alarm_info["threshold_rule"]["period"]
    alarm_condition = alarm_meter_name + " " + comparison_operator + " " + str(threshold) + " during " + str(period) + " s"
    
    return alarm_condition

#import sendmail
#alarm_info = get_alarm_info('6517ecea-f3bc-4f8b-9d67-2b7b56ebd8c9')
#if is_need_send_email(alarm_info):
#    alarm_condition = get_alarm_condition_info(alarm_info)
#    print alarm_condition
#    sendmail.send(alarm_condition)
