#coding:utf-8

import base64
import json
from nova.openstack.common import log as logging
import requests

LOG = logging.getLogger(__name__)

class Request(object):
    """
    向CServer发送请求类
    """
    
    def __init__(self, host, username, password, domain="internal"):
        cert = "Basic " + base64.b64encode('%s@%s:%s' %(username,domain,password))
        self._host = host
        self._headers = {
                        'Host': 'identity.api.openstack.org',
                        'Content-Type': 'application/xml',
                        'Accept': 'application/json',
                        'Accept-Encoding': 'gzip, deflate',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Cookie': 'username=root; kimchiLang=zh_CN',
                        'Authorization': cert,
                        'X-Requested-With': 'XMLHttpRequest',
                                }
        

    def getServiceURL(self, url, port=443):
        return "https://" + self._host + ":" + str(port) + url


    def getRequestInfo(self, url):
        """执行get请求"""
        try:        
            request = requests.get(self.getServiceURL(url), headers=self._headers, verify=False)
            if request.ok:
                return request.json()
            else:
                LOG.info("Get request failed: %s, url: %s" % (request.content, url))
            
        except requests.exceptions.ConnectionError, e:
            LOG.info("Get request connect failed, url: %s" % url)
            
        return False
                
    def postRequestInfo(self, url, info):
        """执行post请求"""
        try:        
            request = requests.post(self.getServiceURL(url), info, headers=self._headers, verify=False)
            if request.ok:
                return request.json()
            else:
                LOG.info("Post request failed: %s, url: %s" % (request.content, url))
            
        except requests.exceptions.ConnectionError, e:
            LOG.info("Post request connect failed, url: %s" % url)
            
        return False
            
    def putRequestInfo(self, url, info):
        """执行put请求"""
        try:        
            request = requests.put(self.getServiceURL(url), data=json.dumps(info), headers=self._headers, verify=False)
            if request.ok:
                return request.json()
            else:
                LOG.info("Put request failed: %s, url: %s" % (request.content, url))
            
        except requests.exceptions.ConnectionError, e:
            LOG.info("Put request connect failed, url: %s" % url)
            
        return False
    
        
    def deleteRequestInfo(self, url, info):
        """执行delete请求"""
        try:        
            request = requests.delete(self.getServiceURL(url), data=info, headers=self._headers, verify=False)
            if request.ok:
                return request.json()
            else:
                LOG.info("Delete request failed: %s, url: %s" % (request.content, url))
            
        except requests.exceptions.ConnectionError, e:
            LOG.info("Delete request connect failed, url: %s" % url)
            
        return False
 
