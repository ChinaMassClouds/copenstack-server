# -*- coding: utf-8 -*-
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 Justin Santa Barbara
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import requests
import json
import os
import logging

LOG = logging.getLogger(__name__)

class RequestApi(object):
    def __init__(self):
        super(RequestApi,self).__init__()
        self.port = '5001'
        self.openstack_cfg = '/etc/openstack.cfg'
        self.headers = {
                        'Host': 'identity.api.openstack.org',
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'Accept-Encoding': 'gzip, deflate',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Cookie': 'username=root; kimchiLang=zh_CN',
                        'X-Requested-With': 'XMLHttpRequest',
                                }
    
    def getControlerip(self):
        keyword = 'CONTROLLER_NODE_IP='
        if os.path.exists(self.openstack_cfg):
            with open(self.openstack_cfg,'r') as f:
                for line in f.readlines():
                    if line and line.startswith(keyword):
                        return line[len(keyword):].replace('\n','')
        return '127.0.0.1'
    
    def wholeUrl(self,url):
        controler_ip = self.getControlerip()
        return 'http://%s:%s/%s' % (controler_ip,self.port,url)
    
    def getRequestInfo(self, url, info={}):
        """
                    获取请求的信息
        @url 请求的url信息
        """
        try:
            url = self.wholeUrl(url)
            request = requests.get(url, data=json.dumps(info), headers=self.headers, verify=False)
                        
            if request.ok:
                return request.json()
            elif request.status_code == 403:
                return "forbidden"
            else:
                return None
        except Exception as e:
            return None
        
        
    def postRequestInfo(self, url, info):
        """
                    执行相应的请求操作
        @url 请求的url信息，
        @info 执行操作时需要的数据
        @isNeedReturnValue 执行完操作时，是否需要返回相应的信息
        """
        url = self.wholeUrl(url)
        request = None
        try:
            request = requests.post(url, data=json.dumps(info), headers=self.headers)
        except Exception as e:
            pass
        if request and request.ok:
            return request.json()
        elif request and request.status_code == 403:
            return "forbidden"
        else:
            return None
            
    def deleteRequestInfo(self, url, info={}):
        """
                    执行相应的请求操作
        @url 请求的url信息，
        """
        url = self.wholeUrl(url)
        request = requests.delete(url, data=json.dumps(info), headers=self.headers)
        if request.ok:
            return request.json()
        else:
            return None
            
    def putRequestInfo(self, url, info, tenantName, isNeedReturnValue=False):
        url = self.wholeUrl(url)
        request = requests.put(url, data=json.dumps(info), headers=self.headers)
                
        if request.status_code == 403:
            return "forbidden"
            
        if request.ok:
            return request.json()
        
        
def vcenter_vms(plat_name):
    try:
        request_api = RequestApi()
        vms = request_api.getRequestInfo('api/heterogeneous/platforms/vcenter/vms',{'name':plat_name}) or []
        if vms and type(vms) == type([]):
            return vms
        elif vms and type(vms) == type({}) \
                and vms.get('action') == 'failed' \
                and vms.get('errormsg'):
            LOG.error('Error to query vcenter vms: %s' % str(vms.get('errormsg')))
    except Exception as e:
        LOG.error('Error to query vcenter vms: %s' % str(e))
    return []
    
def cserver_vms(plat_name):
    try:
        request_api = RequestApi()
        vms = request_api.getRequestInfo('api/heterogeneous/platforms/cserver/vms',{'name':plat_name}) or []
        if vms and type(vms) == type([]):
            return vms
        elif vms and type(vms) == type({}) \
                and vms.get('action') == 'failed' \
                and vms.get('errormsg'):
            LOG.error('Error to query cserver vms: %s' % str(vms.get('errormsg')))
    except Exception as e:
        LOG.error('Error to query cserver vms: %s' % str(e))
    return []

def_vcenter_vms = vcenter_vms
def_cserver_vms = cserver_vms