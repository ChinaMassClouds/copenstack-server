#!/usr/bin/env python
#-*- coding: utf-8 -*-
#update:2014-08-30 by liufeily@163.com

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse,HttpResponseRedirect
from django.shortcuts import render_to_response,RequestContext
from django.db import connection
from django.core.urlresolvers import reverse
from config import Paths,OPENSTACK_DEPLOY_CONF
from mplatform.utils.commondef import allProductSites
import uuid
import os
import time
import json
import ConfigParser 
import commands

HOST_STATUS = {}
DISK_MAX = 0

def dhcpIsActive():
    is_active = False
    (s,o) = commands.getstatusoutput('systemctl status dhcpd')
    if s == 0 and 'Active: active' in o:
        is_active = True
    return is_active

@login_required
def Home(request):        
    to_new = '1'
    env_name = ''
    if os.path.exists(OPENSTACK_DEPLOY_CONF): # 云环境已存在
        to_new = '0'
        # 获取云环境名称
        configparser = ConfigParser.ConfigParser()
        configparser.read(OPENSTACK_DEPLOY_CONF)
        if configparser.has_option('cenvironmentname', 'cenvironmentname'):
            env_name = configparser.get('cenvironmentname', 'cenvironmentname') 

    return render_to_response('pages/guide.html',{'dhcpIsActive':dhcpIsActive(),'env_name':env_name,'to_new':to_new,'request':request},RequestContext(request))


def About(request):
    versionFile = '/etc/default/version'
    version = ''
    release = ''
    if os.path.exists(versionFile):
        f = open(versionFile,'r')
        for line in f.readlines():
            line = line.replace('\n','')
            if line.startswith('VERSION='):
                version = line.split('=')[1]
            if line.startswith('RELEASE='):
                release = line.split('=')[1]
    kwargs = {'version':version,'release':release}
    return render_to_response('about.html',{'request':request,'kwargs':kwargs},RequestContext(request))
