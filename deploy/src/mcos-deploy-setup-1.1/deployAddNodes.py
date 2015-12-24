#!/usr/bin/python
import sys
import os
import string
import pexpect
import paramiko
import string
import socket
import ConfigParser
from socket import *
from time import sleep
from time import ctime
import threading
import logging
import logging.handlers
import sys
reload(sys)
sys.setdefaultencoding('utf8')

handler = logging.handlers.RotatingFileHandler('/var/log/openstackDeploy.log',maxBytes = 1024*1024, backupCount = 5)
fmt = '%(asctime)s-%(filename)s:%(lineno)s-%(name)s-%(message)s'
formatter = logging.Formatter(fmt)
handler.setFormatter(formatter)
logger = logging.getLogger('*****')
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

conf = ConfigParser.ConfigParser()
conf.read("/etc/openstack_deploy.conf")
if not conf.has_section("deployinfo"):
	conf.add_section("deployinfo")
	conf.set("deployinfo","deploystatus","nodeploy")
lastDeployStatus = conf.get("deployinfo","deploystatus")
conf.set("deployinfo","deploystatus","deploying")
conf.write(open("/etc/openstack_deploy.conf","w"))

list = []
if os.path.exists("/etc/nodeHardwareInfo/nodesum.conf"):
	confNodeSum = ConfigParser.ConfigParser()
	confNodeSum.read("/etc/nodeHardwareInfo/nodesum.conf")
	if confNodeSum.has_section("newaddnodes"):
		nodesum = confNodeSum.get("newaddnodes","newnodesum").strip('\n')
		for i in range(string.atoi(nodesum)):
			newNodeName = confNodeSum.get("newaddnodes","node"+str(i+1)).strip('\n')
			list.append(newNodeName)

globalStr = ""
BUFSIZ = 1024
 
def creatSiteFile():
	logger.info('Start creatSiteFile')
	fSite = open("/etc/puppet/manifests/site.pp",'w')
	if not os.path.isdir('/etc/puppet/manifests/nodes/'):
                os.makedirs('/etc/puppet/manifests/nodes/')
	fSite.truncate()
	for i in range(1,string.atoi(conf.get("nodenum","nodesum"),10)+1):
		fSite.write("import \"nodes/"+ conf.get("nodehostname","node"+str(i)).strip('\n') +".pp\"\n")
		fNode = open('/etc/puppet/manifests/nodes/'+ conf.get("nodehostname","node"+str(i)).strip('\n') +'.pp','w')
		fNode.write("node \'" + conf.get("nodehostname","node"+str(i)).strip('\n') + "\' {\n")
		fNode.write('\t'+"include globalfile\n")
		fNode.write("}\n")
		fNode.close()
	fSite.close()
	logger.info('CreatSiteFile Over')

def creatNodeFile(nodeName,classNames):
	logger.info('start CreatNodeFile')
	if not os.path.isdir('/etc/puppet/manifests/nodes/'):
		os.makedirs('/etc/puppet/manifests/nodes/')
	fNode = open('/etc/puppet/manifests/nodes/'+nodeName+'.pp','w')
	fNode.write("node \'" + nodeName + "\' {\n")
	fNode.write('\t'+"include globalfile\n")
	for className in classNames.split('&'):
		fNode.write('\t'+"include "+ className+ "\n")
	fNode.write("}\n")
	fNode.close()
	logger.info('CreatNodeFile Over')

def getServiceStatus(ip, cmd):
	ret = -1
	ssh = pexpect.spawn('ssh root@%s "%s"' % (ip, cmd))
	try:
		i = ssh.expect(['password:', 'continue connecting (yes/no)?'], timeout=5)
		if i == 0 :
			ssh.sendline(conf.get("nodeloginfo","nodepasswd").strip('\n'))
			ssh.sendline(cmd)
			rInfo=ssh.read()
			if "Active: active (running)" in rInfo:
				ret = 0
			else:
				ret = -1
		elif i == 1:
			ssh.sendline('yes\n')
			ssh.expect('password: ')
			ssh.sendline(conf.get("nodeloginfo","nodepasswd").strip('\n'))
			ssh.sendline(cmd)
			r = ssh.read()
			if "Active: active (running)" in r:
				ret = 0
			else:
				ret = -1
	except pexpect.EOF:
		print "EOF"
		ssh.close()
		ret = -1
	except pexpect.TIMEOUT:
		print "TIMEOUT"
		ssh.close()
		ret = -2
	return ret

def getServiceStatusManayTimes(ip,cmd,time=3):
	for i in range(20):
		if 0 == getServiceStatus(ip,cmd):
			return 0
		sleep(time)
	return -1
class MyThread(threading.Thread):
	#print("come in mythread")
	def __init__(self,threadName,event):
		threading.Thread.__init__(self,name=threadName)
                os.system("for pid in `lsof -i:21567 | grep -v PID | awk '{print $2}'`; do kill -9 $pid;done")

		self.threadEvent = event
		HOST = conf.get("nodeip","master.server.com_ip").strip('\n')
		PORT = 21567
		BUFSIZ = 1024
		ADDR = (HOST, PORT)
		s1 = self.tcpSerSock = socket(AF_INET, SOCK_STREAM)
		s2 = self.tcpSerSock.bind(ADDR)
		s3 = self.tcpSerSock.listen(5)
#		#print ("s1 = %s , s2 = %s, s3 = %s" %(s1 ,s2, s3))
		logger.info("socket = %s , band = %s, listen = %s" %(s1 ,s2, s3))
	def run(self):
		while True:
			#print 'waiting for connection...'
			logger.info('waiting for connection...')
			tcpCliSock, addr = self.tcpSerSock.accept()
		#	#print '...connected from:', addr
			logger.info('...connected from:'+str(addr))
			while True:
				data = tcpCliSock.recv(BUFSIZ)
				if not data:
					#print ("data is null!")
					logger.info("return deploy info is null!")
					break
				tcpCliSock.send('[%s] %s' %(ctime(), data))
				#print("send info is:%s,%s" %(ctime(),data))
				if("success" in data or "failed" in data):
					global globalStr
					globalStr = data
					#print("come in set()")
					self.threadEvent.set()
			tcpCliSock.close()
		tcpSerSock.close()

def getNeutronScriptToController():
	if conf.get("networkinfo","networktype") == 'gre':
		return "network-gre"
	if conf.get("networkinfo","networktype") == 'vlan':
		return "network-vlan"
	if conf.get("networkinfo","networktype") == 'vxlan':
		return "network-vxlan"

def getNeutronScriptToComputer():
	if conf.get("networkinfo","networktype") == 'gre':
		return "computer-gre"
	if conf.get("networkinfo","networktype") == 'vlan':
		return "computer-vlan"
	if conf.get("networkinfo","networktype") == 'vxlan':
		return "computer-vxlan"

def execRemoteCommond(ip,commond):
	#print("start================ ssh")
	ssh = paramiko.SSHClient()
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	ssh.connect(ip,22,conf.get("nodeloginfo","nodeusername"),conf.get("nodeloginfo","nodepasswd"))
	commond = commond + "> /var/log/" + commond +".log"
	#print ("ip===%s, commond====%s" %(ip, commond))
	stdin, stdout, stderr = ssh.exec_command(commond)
#	for line in stdout:
#		#print line.strip('\n')
	#print stdout.readlines()
	stdout.read()
	#print ("out exec_common_out")
	ssh.close()

def deployOpenstack():
#	creatSiteFile()
	signal = threading.Event()
	checkThead = MyThread('checkThread',signal)
	checkThead.start()
	addNodeList = conf.items("newcomputernodes")
	for addNode in addNodeList:
		addNodeHost = addNode[1]
		opstkCom = getNeutronScriptToComputer()
		if opstkCom == "computer-gre":
			command = "setup-compute-gre-node"
		if opstkCom == "computer-vlan":
			command = "setup-compute-vlan-node"
		if opstkCom == "computer-vxlan":
			command = "setup-compute-vxlan-node"
		execRemoteCommond(conf.get("nodeip",addNodeHost+"_ip"),command)
		execRemoteCommond(conf.get("nodeip",addNodeHost+"_ip"),"ceilometer-snmp")
		signal.wait()
		signal.clear()
		logger.info("##**##&end:"+globalStr)
		if "failed" in globalStr:
			conf.set("deployinfo","deploystatus","deployed")
			conf.write(open("/etc/openstack_deploy.conf","w"))

if __name__ == '__main__':
	deployOpenstack()
	#print("##**##&deployover")
	
	conf.remove_section("newcomputernodes")
	conf.write(open("/etc/openstack_deploy.conf","w"))

	logger.info("##**##&deployover")
	conf.set("deployinfo","deploystatus","deployed")
	conf.write(open("/etc/openstack_deploy.conf","w"))
	#print ("****************************************************")
	#print ("                openstack deploy over               ") 
	#print ("       Landing %s access dashboard          "%conf.get("nodeip",conf.get("componentinfo","controller-novanode0").strip('\n')+"_ip").strip('\n')) 
	#print ("****************************************************")
	#logger.info("****************************************************")
	#logger.info("                openstack deploy over               ")
	#logger.info("       Landing %s access dashboard          "%conf.get("nodeip",conf.get("componentinfo","controller-novanode0").strip('\n')+"_ip").strip('\n'))
	#logger.info("****************************************************")
	os._exit(0)
