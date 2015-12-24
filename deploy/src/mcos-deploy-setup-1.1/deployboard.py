#!/usr/bin/python
# -*- coding: utf-8 -*-
        
import socket,sys
import time, json, os
import ConfigParser
import string

confNodeSum = ConfigParser.ConfigParser()
confNodeSum.add_section("nodesum")
confNodeSum.read("/etc/nodeHardwareInfo/nodesum.conf")
if confNodeSum.has_section("newaddnodes"):
	confNodeSum.remove_section("newaddnodes")

conf = ConfigParser.ConfigParser()
conf.read("/etc/openstack_deploy.conf")
if not conf.has_section("deployinfo"):
        conf.add_section("deployinfo")
        conf.set("deployinfo","deploystatus","nodeploy")
	conf.write(open("/etc/openstack_deploy.conf","w"))
lastDeployStatus = conf.get("deployinfo","deploystatus")

#要求客户节节点发送Puppet认证请求的信息
msg = "Puppet client node Authentication"

#要求客户节点发送硬件配置的信息
msg = "Request Hardware Information"
if len(sys.argv) > 1:
	msg = sys.argv[1]

nodesum = 0
newnodesum = 0
list = []
if os.path.exists("/etc/nodeHardwareInfo/nodesum.conf") and msg == "Request Hardware Information":
	nodesum = confNodeSum.get("nodesum","num").strip('\n')
	nodesum = string.atoi(nodesum)
	for i in range(nodesum):
		fread = open("/etc/nodeHardwareInfo/node"+str(i+1)+".info","r")
		fjson = json.load(fread)
		list.append(fjson['macaddress'])

desc = ('<broadcast>',6666)
s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
s.sendto(msg, desc)
print "Broadcast the message %s" % msg
if msg == "Puppet client node Authentication":
	os._exit(0)
time.sleep(3)
if not os.path.isdir('/etc/nodeHardwareInfo/'):
	os.makedirs('/etc/nodeHardwareInfo/')

while True:
	data,addr = s.recvfrom(8192)
	if not len(data):
		break
	print "Received from %s:%s"%(data,addr)
	print type(data), data
	if msg == "Request Hardware Information":
		jsonData = json.loads(data)
		if jsonData['macaddress'] in list:
			continue
#		tmp = string.atoi(nodesum)
#		tmp = tmp + 1
#		nodesum = str(tmp)
		nodesum = nodesum + 1
		if lastDeployStatus == "success":
			if not confNodeSum.has_section("newaddnodes"):
				confNodeSum.add_section("newaddnodes")
			newnodesum = newnodesum + 1
			confNodeSum.set("newaddnodes","newnodesum",str(newnodesum))
			confNodeSum.set("newaddnodes","node"+str(newnodesum),"node"+str(nodesum)+".localdomain")
		confNodeSum.set("nodesum","num",str(nodesum))
		confNodeSum.write(open("/etc/nodeHardwareInfo/nodesum.conf","w"))
		with open("/etc/nodeHardwareInfo/node"+str(nodesum)+".info","w") as f:
			json.dump(jsonData,f)
		
