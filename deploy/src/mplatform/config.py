#coding=utf-8
# Project Chost
#
# Copyright IBM, Corp. 2013
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA

import os
import threading

from ConfigParser import SafeConfigParser


__version__ = "1.1.1"
__release__ = "0"

DEFAULT_LOG_LEVEL = "debug"
VERSION_FILE = '/etc/default/version'
chostLock = threading.Lock()

# openstack 部署日志
OPENSTACK_DEPLOY_LOG = '/var/log/openstackDeploy.log'
# 节点信息目录
NODE_INFO_FILES_DIR = '/etc/nodeHardwareInfo/'
NODESUM_FILE = NODE_INFO_FILES_DIR + 'nodesum.conf'
# 节点配置目录
NODE_CFG_FILES_DIR = '/etc/nodesconf/'
# 云环境配置信息
OPENSTACK_DEPLOY_CONF = '/etc/openstack_deploy.conf'
# 节点顶级域名
NODE_DOMAIN_NAME = '.localdomain'

def get_version():
    version = ''
    if os.path.exists(VERSION_FILE):
        verfile = open(VERSION_FILE,'r')
        lines = verfile.readlines()
        for line in lines:
            if 'VERSION' in line:
                version = line[8:]
                break
    return version

def get_release():
    release = ''
    if os.path.exists(VERSION_FILE):
        verfile = open(VERSION_FILE,'r')
        lines = verfile.readlines()
        for line in lines:
            if 'BUILD_DATE' in line:
                release = line[11:]
                break
    return release

def get_ntptask_path():
    return os.path.join(paths.state_dir, 'ntptask')


class Paths(object):

    def __init__(self):
        self.prefix = self.get_prefix()
        self.state_dir = '/var/lib/mplatform'
        self.log_dir = '/var/log/mplatform'
        self.conf_dir = '/etc/mplatform'
        self.sys_conf_dir = '/etc/sysconfig'
        self.src_dir = '/usr/lib/python2.7/site-packages/mplatform'
        self.basic_upgrade_dir = '/usr/local/src/' # 基础升级包上传位置
        self.unit_upgrade_dir = '/var/www/html/openstackrpmrepo/' # 组件升级包上传位置
        self.deploy_node_config = '/etc/deploy_node_config'
        self.license_dir = '/usr/local/authorization/'
        self.license_file = '/usr/local/authorization/license'
        self.license_date_file = '/usr/local/authorization/license_date'
        self.tmp_license_file = '/usr/local/authorization/licenseTmp'
        self.default_dhcp_age = 10

    def get_prefix(self):
            base = os.path.dirname(__file__)
            return base
            #print base
             #base =

    def add_prefix(self, subdir):
        return os.path.join(self.prefix, subdir)



paths = Paths()



def _get_config():
    config = SafeConfigParser()
    config.add_section("server")
    config.set("server", "host", '0.0.0.0')
    config.set("server", "proxy_port", "8080")
    config.set("server", "port", "8000")
    config.set("server", "path", paths.get_prefix())
    config.add_section("logging")
    #config.set("logging", "log_dir", paths.log_dir)
    #config.set("logging", "log_level", DEFAULT_LOG_LEVEL)
    #config.set("logging", "debug_log_level", DEFAULT_LOG_LEVEL)


   # config_file = os.path.join(paths.conf_dir, 'mplatform.conf')
   # if os.path.exists(config_file):
    #    config.read(config_file)
    return config

config = _get_config()


if __name__ == '__main__':
    print paths.prefix
