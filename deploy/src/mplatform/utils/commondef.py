#!/usr/bin/python
# -*- coding: utf-8 -*-

from mplatform.utils.db import dbbase
from mplatform.utils.net import network
import ethtool
import os
import commands
import socket
import re
import json
import shutil
import traceback

# 所有产品的站点信息
def allProductSites():
    return []

# 将注册信息写入cache
def writeSignCache(sign_hosts):
    pass
    

# 获取注册信息cache
def getSignCache():
    return {}


# 把管理中心的计算机名映射同步到运行端和客户端
def syncHostsConfig(target_ip = None):
    hosts = ''
    with open("/etc/hosts",'r') as f:
        for line in f.readlines():
            if line:
                arr = line.split()
                if len(arr) > 1 and re.match('^\d',arr[0]) and not arr[0].startswith('127.0.0.1'):
                    hosts += line
    msg = 'hosts_cfg %s' % hosts
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if target_ip:
        s.sendto(msg, (target_ip, 20000))
    else:
        db = dbbase.database()
        hlist = db.select_fetchall("select ip from platdeploy_servicestatus union all select ip from platdeploy_terminalstatus")
        for h in hlist:
            s.sendto(msg, (h['ip'], 20000))
    s.close()
    
"""
获取管理端、运行端、客户端的所有主机
"""
def get_all_hosts():
    hosts = [get_local_ip()]
    sql = "select ip from platdeploy_servicestatus union all select ip from platdeploy_terminalstatus"
    db = dbbase.database()
    res = db.select_fetchall(sql)
    for h in res:
        hosts.append(h.get('ip'))
    hosts.sort()

    return hosts

def get_local_ip():
    ifnames = get_nics()
    for ifname in ifnames:
        config_file='/etc/sysconfig/network-scripts/ifcfg-%s' % ifname
        if os.path.exists(config_file):
            fp = open(config_file,'r')
            is_slave = False
            for line in fp.readlines():
                if line[0] == '#':
                   continue
                if 'SLAVE' in line and 'yes' in line:
                   is_slave = True
                   break
                del line
            if not is_slave:
                try:
                    ip = ethtool.get_ipaddr(ifname)
                    if ip:
                        return ip
                except Exception as e:
                    logger.error(traceback.format_exc())

    return ""

def get_nics():
    print "进入_get_nics"
    nic_list = network.all_ifaces()
    nics = [network.NIC(ifname) for ifname
                in nic_list]
    bridges = [nic for nic in nics if nic.typ == "bridge"]
    vlans = [nic for nic in nics if nic.typ == "vlan"]
    nics = [nic for nic in nics if nic not in bridges + vlans]
    ifnames = [nic.ifname for nic in nics if nic.ifname <> 'lo']
    print "退出_get_nics"
    return ifnames

def get_gateway():
    cmd = "route | grep default | awk '{print $2}'"
    (s,o) = commands.getstatusoutput(cmd)
    if s == 0 and o:
        return str(o)
    return ""