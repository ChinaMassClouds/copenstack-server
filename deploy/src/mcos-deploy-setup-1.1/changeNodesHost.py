#!/usr/bin/python
import sys
import os
import string
import pexpect
import paramiko
import string
import socket
import ConfigParser

conf = ConfigParser.ConfigParser()
conf.read("/etc/openstack_deploy.conf")

def writeNodeHostfile(hostname):
	if not os.path.isdir("/root/nodehost"):
		os.makedirs("/root/nodehost")
	fhost = open("/root/nodehost/hostname","w")
	fhost.write(hostname+'\n')
	fhost.close()

def changeMasterHostfile():
	fhost = open('/etc/hosts','w')
	fhost.write("127.0.0.1   localhost localhost.localdomain localhost4 localhost4.localdomain4\n")
	fhost.write("::1         localhost localhost.localdomain localhost6 localhost6.localdomain6\n")
	for i in range(string.atoi(conf.get("nodenum","nodesum"))+1):
		print("nodenum=%s"+conf.get("nodenum","nodesum"))
		if i==0:
			fhost.write(conf.get("nodeip",conf.get("nodehostname","node"+str(i)).strip('\n')+"_ip")+ " master " +conf.get("nodehostname","node"+str(i)).strip('\n') + '\n')
		else:
			fhost.write(conf.get("nodeip",conf.get("nodehostname","node"+str(i)).strip('\n')+"_ip")+ " " + "node"+str(i) + " " +conf.get("nodehostname","node"+str(i)).strip('\n') + '\n')
	fhost.close()

def sendNodeHostNameFile(nodeIp,hostname,num):
	print("connecting    %s " %nodeIp)
	writeNodeHostfile(hostname)
	trans = paramiko.Transport((nodeIp,22))
	trans.connect(username=conf.get("nodeloginfo","nodeusername").strip('\n'), password=conf.get("nodeloginfo","nodepasswd").strip('\n'))
	sftp = paramiko.SFTPClient.from_transport(trans)
	remotepath1 = '/etc/hosts'
	localpath1 = '/etc/hosts'
	sftp.put(localpath1,remotepath1)

	remotepath2 = '/etc/hostname'
	localpath2 = '/root/nodehost/hostname'
	sftp.put(localpath2,remotepath2)

	remotepath3 = '/etc/openstack.cfg'
	localpath3 = '/etc/nodesconf/node' + str(num) + '.cfg'
	print (localpath3)
	sftp.put(localpath3,remotepath3)	

		
	remotepath4 = '/usr/local/license_date'
	localpath4 = '/usr/local/authorization/license_date'
	if os.path.exists(localpath4):
		sftp.put(localpath4,remotepath4)

	remotepath5 = '/usr/local/probation'
	localpath5 = '/usr/local/authorization/probation'
	if os.path.exists(localpath5):
		sftp.put(localpath5,remotepath5)


if __name__ == '__main__':
	changeMasterHostfile()
	for i in range(1,string.atoi(conf.get("nodenum","nodesum"),10)+1):
		sendNodeHostNameFile(conf.get("nodeip",conf.get("nodehostname","node"+str(i)).strip('\n')+"_ip"),conf.get("nodehostname","node"+str(i)),i)	
