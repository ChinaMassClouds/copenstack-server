#!/usr/bin/env python
#-*- coding: utf-8 -*-

from django.http import HttpResponse,HttpResponseRedirect
from django.shortcuts import render_to_response,RequestContext
from django.contrib.auth.decorators import login_required
from django.core.servers.basehttp import FileWrapper
from config import Paths,OPENSTACK_DEPLOY_CONF
import paramiko
import logging
import ctypes
import os
import tempfile
import datetime
import traceback
import re
import ConfigParser
import base64

logger = logging.getLogger(__name__)

LIBMCOSLBASER = ctypes.CDLL('libmcoslbaser.so', use_errno=True)

def getControllers():
    ips = []
    try:
        if os.path.exists(OPENSTACK_DEPLOY_CONF):
            cfgparser = ConfigParser.ConfigParser()
            cfgparser.read(OPENSTACK_DEPLOY_CONF)
            index = 0
            while cfgparser.has_option('componentinfo', 'controller-horizonnode' + str(index)):
                node_name = cfgparser.get('componentinfo', 'controller-horizonnode' + str(index))
                if cfgparser.has_option('nodeip', node_name + '_ip'):
                    node_ip = cfgparser.get('nodeip', node_name + '_ip')
                    if node_ip:
                        ips.append(node_ip)
                index += 1
    except Exception as e:
        logger.error(traceback.format_exc())
    return ips

def getNodeLoginInfo():
    username = ''
    password = ''
    try:
        if os.path.exists(OPENSTACK_DEPLOY_CONF):
            conf = ConfigParser.ConfigParser()
            conf.read(OPENSTACK_DEPLOY_CONF)
            if conf.has_option('nodeloginfo', 'nodeusername'):
                username = conf.get('nodeloginfo', 'nodeusername')
            if conf.has_option('nodeloginfo', 'nodepasswd'):
                password = conf.get('nodeloginfo', 'nodepasswd')
    except Exception as e:
        logger.error(traceback.format_exc())
    return (username,password)

def sendLicenseToControllers():
    try:
        localpath1 = Paths().license_date_file
        end_date_str = getLicenseEndDate()
        with open(localpath1,'w') as f:
            f.write(base64.b64encode(end_date_str))
        
        (user_name,passwd) = getNodeLoginInfo()
        if os.path.exists(localpath1) and user_name and passwd:
            for ip in getControllers():
                try:
                    trans = paramiko.Transport((ip,22))
                    trans.connect(username=user_name, password=passwd)
                    sftp = paramiko.SFTPClient.from_transport(trans)
                    remotepath1 = '/usr/local/license_date'
                    sftp.put(localpath1,remotepath1)
                except Exception as ee:
                    logger.error(traceback.format_exc())
    except Exception as e:
        logger.error(traceback.format_exc())

@login_required
def getLicenseCpuNo(request):
    try:
        if getProbationEndDate():
            return HttpResponse('probation')
        if not checkLicenseDate():
            return HttpResponse('outdate')
        license_info = readLicense()
        keyword = 'cpuno='
        if license_info:
            for line in license_info.split('\n'):
                if line and line.startswith(keyword):
                    res = line[len(keyword):].replace('\n','')
                    pattern = re.compile(r'^\d+$')
                    if pattern.match(res):
                        return HttpResponse(res)
    except Exception as e:
        logger.error(traceback.format_exc())
    return HttpResponse('error')

def getProbationEndDate():
    try:
        probation_file = '/usr/local/authorization/probation'
        if os.path.exists(probation_file):
            with open(probation_file,'r') as f:
                str = f.read().replace('\n','')
                end_date_str = base64.b64decode(str)
                today = datetime.datetime.today()
                today_str = datetime.datetime.strftime(today,'%Y-%m-%d')
                if cmp(today_str,end_date_str) <= 0:
                    return end_date_str
    except Exception as e:
        logger.error(traceback.format_exc())
    return ''



def getLicenseEndDate():
    try:
        license_info = readLicense()
        keyword = 'enddata='
        if license_info:
            for line in license_info.split('\n'):
                if line and line.startswith(keyword):
                    end_date_str = line[len(keyword):].replace('\n','')
                    return end_date_str
    except Exception as e:
        logger.error(traceback.format_exc())
    return ''

def checkLicenseDate():
    try:
        end_date_str = getLicenseEndDate()
        if end_date_str:
            today = datetime.datetime.today()
            today_str = datetime.datetime.strftime(today,'%Y-%m-%d')
            if cmp(today_str,end_date_str) <= 0:
                return True
    except Exception as e:
        logger.error(traceback.format_exc())
    return False

@login_required
def downloadHardinfo(request):
    try:
        (fd, pipe) = tempfile.mkstemp()
        
        file_name2 = ctypes.create_string_buffer(4096)
        file_name2.value = pipe
        LIBMCOSLBASER.create_host_info_file(file_name2)
    
        f = open(pipe)
        os.remove(pipe)
        response = HttpResponse(FileWrapper(f), content_type='text/plain')
        response['Content-Disposition'] = 'attachment; filename=hardinfo'
        return response
    except Exception as e:
        logger.error(traceback.format_exc())
        return HttpResponse('')

@login_required
def getHardInfo(request):
    try:
        hardinfo = ctypes.create_string_buffer(4096)
        buffer_len = ctypes.c_int(4096)
        LIBMCOSLBASER.get_host_info(hardinfo,buffer_len)
        return HttpResponse(hardinfo.value)
    except Exception as e:
        logger.error(traceback.format_exc())
        return HttpResponse('')

@login_required
def getLicenseInfo(request):
    license_info_res = ''
    try:
        res = ''
        license_info = readLicense()
        if license_info:
            res = pickLicenseInfo(license_info)
        else:
            probationEndDate = getProbationEndDate()
            if probationEndDate:
                res = 'probation:' + probationEndDate
        return HttpResponse(res)
    except Exception as e:
        logger.error(traceback.format_exc())
        return HttpResponse('')

def readLicense():
    try:
        license_info = ctypes.create_string_buffer(4096)
        license_path = Paths().license_file
        res = ''
        if os.path.exists(license_path): # 存在授权文件
            file_name2 = ctypes.create_string_buffer(4096) 
            file_name2.value = license_path
            buffer_len2 = ctypes.c_int(4096)
            LIBMCOSLBASER.get_license_info(file_name2,license_info,buffer_len2)
            return license_info.value
    except Exception as e:
        logger.error(traceback.format_exc())
    return ''

@login_required
def uploadLicense(request):
    try:
        file =  request.FILES.get('file')
        _license_dir = Paths().license_dir
        if not os.path.exists(_license_dir):
            os.makedirs(_license_dir, 0755)
        fd = open(Paths().tmp_license_file, 'wb')
        for chunk in file.chunks():
            fd.write(chunk)
        fd.close()
    except Exception as e:
        logger.error(traceback.format_exc())
    return HttpResponse(getTmpLicenseInfo())

def getTmpLicenseInfo():
    try:
        file_name2 = ctypes.create_string_buffer(4096) 
        file_name2.value = Paths().tmp_license_file
        license_info = ctypes.create_string_buffer(4096)
        buffer_len2 = ctypes.c_int(4096)
        result = LIBMCOSLBASER.get_license_info(file_name2,license_info,buffer_len2)
        return pickLicenseInfo(license_info.value)
    except Exception as e:
        logger.error(traceback.format_exc())
        return ''

def pickLicenseInfo(licenseinfo):
    res = ''
    pick_lines = ['producer',
                  'product',
                  'customer',
                  'startdata',
                  'enddata',
                  'lictype',
                  'version_types',
                  'authtype',
                  'userno',
                  'cpuno',
                  'vdino',
                  'idvno',
                  'Ukeysno',
                  'desktopno',
                  'onlineuserno']
    license_lines = licenseinfo.split('\n')
    for line in license_lines:
        for pk in pick_lines:
            if line.startswith(pk + '='):
                res += line + '\n'
                break
    return res

@login_required
def licenseok(request):
    try:
        os.rename(Paths().tmp_license_file, Paths().license_file)
        sendLicenseToControllers()
        return HttpResponse('success')
    except Exception as e:
        logger.error(traceback.format_exc())
        return HttpResponse('fail')
