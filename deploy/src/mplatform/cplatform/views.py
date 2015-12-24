#!/usr/bin/env python
#-*- coding: utf-8 -*-

from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from config import Paths, NODE_INFO_FILES_DIR, NODESUM_FILE, OPENSTACK_DEPLOY_CONF,\
        NODE_DOMAIN_NAME, NODE_CFG_FILES_DIR, OPENSTACK_DEPLOY_LOG
from django.utils import log
from django.contrib import auth
from django.views.decorators.csrf import csrf_exempt
import json
import os
import ConfigParser 
import commands
import time
import subprocess
import shutil
import paramiko
import threading
import traceback
import re

logger = log.getLogger(__name__)

# 该常量与JS保持一致
# --------------
# 节点类型与网卡类型对应关系（必须的网卡类型）：
# 网络节点包含的网络：数据网络，存储网络，管理网络和外部网络
# 计算节点包含的网络：数据网络，存储网络，管理网络
# 其他节点：管理网络
NODETYPE_NETTYPE_NESSESARY = {
                    'Controller':['managenet'],
                    'Compute':['managenet','datanet'],
                    'Database':['managenet'],
                    'RabbitMQ':['managenet'],
                    'Neutron':['managenet','datanet'],
                    'Storage-Cinder':['managenet'] }

@login_required
def basicUpgrade(request):
    (s,o) = commands.getstatusoutput('')
    if s != 0:
        logger.error('error in basicUpgrade: %s' % str(o))
        return HttpResponse('fail')
    return HttpResponse('success')

@login_required
def unitUpgrade(request):
    (s,o) = commands.getstatusoutput('')
    if s != 0:
        logger.error('error in unitUpgrade: %s' % str(o))
        return HttpResponse('fail')
    return HttpResponse('success')

# 创建yum源
def createRepo(dir):
    (s,o) = commands.getstatusoutput("createrepo %s" % dir)
    if s == 0:
        return 'success'
    else:
        logger.error('error in createRepo:%s' % str(o))
        return 'createRepo_fail'

@login_required
def ajaxCreateRepo(request):
    return HttpResponse(createRepo(Paths().unit_upgrade_dir))

# 删除文件
def delFile(dir,filename):
    if dir and filename and os.path.exists(dir + filename):
        try:
            os.remove(dir + filename)
            return 'success'
        except Exception as e:
            logger.error(traceback.format_exc())
    return 'fail'

# 遍历文件夹中的文件
def listDirFiles(dir):
    res = []
    if os.path.exists(dir):
        files = os.listdir(dir)
        for f in sorted(files,key=str.lower):
            if os.path.isfile(dir + f):
                res.append({'name':f})

    return res

@login_required
def delUnitRpm(request):
    filenameArr = json.loads(request.POST.get('filename'))
    res = 'fail'
    for f in filenameArr:
        res = delFile(Paths().unit_upgrade_dir,f)
        if res != 'success':
            break
    if res == 'success':
        res = createRepo(Paths().unit_upgrade_dir)
    return HttpResponse(res)

@login_required
def listUnitRpms(request):
    res = listDirFiles(Paths().unit_upgrade_dir)
    return HttpResponse(json.dumps(res))

@login_required
def delBasicIso(request):
    res = delFile(Paths().basic_upgrade_dir,request.POST.get('filename'))
    return HttpResponse(res)

@login_required
def listBasicIsos(request):
    res = listDirFiles(Paths().basic_upgrade_dir)
    f_res = []
    for f in res:
        if f.get('name').endswith('.iso'): # 只显示iso文件
            f_res.append(f)
    return HttpResponse(json.dumps(f_res))

def CombineChunks(infoDic,final_path,upgrade_dir):
    try:
        file_UUID = infoDic.get("fileUUID")
        chunk_dir = upgrade_dir + file_UUID + '/'
        wholefile_size = infoDic.get("size")
        file_name = infoDic.get("name")
        chunks = infoDic.get("chunks")
        retry = 0
        timeout = False
        
        # 合并切片之前，先确认所有切片都已上传完成，如果超过 20 分钟切片还未上传完成，则取消合并
        while True:
            if retry > 1200:
                timeout = True
                break
            retry = retry + 1
            finish_size = 0
            for ch in os.listdir(chunk_dir):
                finish_size = finish_size + os.path.getsize(chunk_dir + ch)
            if int(finish_size) >= int(wholefile_size):
                break
            time.sleep(1)
        
        # 开始合并
        if not timeout:
            final_file = open(final_path, 'wb')
            for i in range(int(chunks)):
                chunk_file = open(chunk_dir + file_UUID + '__' + str(i), 'rb')
                final_file.write(chunk_file.read())
                chunk_file.close()
            final_file.close()
            
        # 合并完成，删除存放切片的临时目录
        shutil.rmtree(chunk_dir)
    except Exception as e:
        logger.error(traceback.format_exc())
    

def SaveChunkFile(infoDic,fileDic,upgrade_dir):
    try:
        file_UUID = infoDic.get("fileUUID")
        chunk_dir = upgrade_dir + file_UUID + '/'
        file_name = infoDic.get("name")
        chunk_index = infoDic.get("chunk")
        src_file = fileDic.get('file')
        
        # 可能会出现多个线程同时创建目录的情况，忽略错误
        try:
            if not os.path.exists(chunk_dir):
                os.makedirs(chunk_dir)
        except Exception as e:
            pass
            
        chunk_path = chunk_dir + file_UUID + '__' + str(chunk_index)
        
        chunk_file = open(chunk_path, 'wb')
        for chunk in src_file.chunks():
            chunk_file.write(chunk)
        chunk_file.close()
    except Exception as e:
        logger.error(traceback.format_exc())
    
@login_required
@csrf_exempt
def uploadBasicIso(request):
    try:
        chunks = request.POST.get("chunks")
        chunk_index = request.POST.get("chunk")
        
        # 保存切片文件
        if chunks: 
            th = threading.Thread(target=SaveChunkFile,args=(request.POST,request.FILES,Paths().basic_upgrade_dir))
            th.start()
            
        file_UUID = request.POST.get("fileUUID")
        iso_name = request.POST.get("name")
        iso_path = Paths().basic_upgrade_dir + iso_name.encode('utf-8')
        final_path = iso_path
    
        # 小文件，直接保存
        if not chunks: 
            final_file = open(final_path, 'wb')
            final_file.write(request.FILES.get('file').read())
            final_file.close()

        # 大文件，到达最后一片时，将切片合并（该线程应该阻塞）
        if chunks and int(chunk_index) == int(chunks) - 1: 
            th2 = threading.Thread(target=CombineChunks,args=(request.POST,final_path,Paths().basic_upgrade_dir))
            th2.start()
            th2.join()
            
        return HttpResponse('success')
    except Exception as e:
        logger.error(traceback.format_exc())
        return HttpResponse('fail')
    
@login_required
@csrf_exempt
def uploadUnitRpm(request):
    try:
        chunks = request.POST.get("chunks")
        chunk_index = request.POST.get("chunk")
        
        # 保存切片文件
        if chunks: 
            th = threading.Thread(target=SaveChunkFile,args=(request.POST,request.FILES,Paths().unit_upgrade_dir))
            th.start()
            
        file_UUID = request.POST.get("fileUUID")
        iso_name = request.POST.get("name")
        iso_path = Paths().unit_upgrade_dir + iso_name.encode('utf-8')
        final_path = iso_path
    
        # 小文件，直接保存
        if not chunks: 
            final_file = open(final_path, 'wb')
            final_file.write(request.FILES.get('file').read())
            final_file.close()

        # 大文件，到达最后一片时，将切片合并（该线程应该阻塞）
        if chunks and int(chunk_index) == int(chunks) - 1: 
            th2 = threading.Thread(target=CombineChunks,args=(request.POST,final_path,Paths().unit_upgrade_dir))
            th2.start()
            th2.join()
            
        return HttpResponse('success')
    except Exception as e:
        logger.error(traceback.format_exc())
        return HttpResponse('fail')


@login_required
def getDeployStatus(request):
    try:
        # 判断是否正在部署中
        configparser = None
        if os.path.exists(OPENSTACK_DEPLOY_CONF):
            configparser = ConfigParser.ConfigParser()
            configparser.read(OPENSTACK_DEPLOY_CONF)
            if getOption(configparser, 'deployinfo', 'deploystatus') == 'deploying':
                return HttpResponse('deploying')
        
        # 判断是否部署完成
        if os.path.exists(OPENSTACK_DEPLOY_LOG):
            with open(OPENSTACK_DEPLOY_LOG,'r') as f:
                log_lines = f.readlines()
                reversed_lines = list(reversed(log_lines))
                for line in reversed_lines:#componentinfo', 'keystonenode
                    if line and '##**##&deployover' in line and configparser:
                        c_hostname = getOption(configparser, 'componentinfo', 'keystonenode0')
                        c_ip = getOption(configparser, 'nodeip', (c_hostname or '') + '_ip') or ''
                        return HttpResponse('deployover,%s' % c_ip)
                    elif line and '##**##&end:' in line and ':failed' in line:
                        return HttpResponse('deployfail')
    except Exception as e:
        logger.error(traceback.format_exc())
    return HttpResponse('')

# 获取节点信息文件的个数
def countNodes():
    try:
        if os.path.exists(NODE_INFO_FILES_DIR):
            arr = os.listdir(NODE_INFO_FILES_DIR)
            regexp = re.compile('^node\d+.info$')
            count = 0
            for f in arr:
                if regexp.match(f):
                    count += 1
            return count
    except Exception as e:
        logger.error(traceback.format_exc())
    return 0

@login_required
def deleteNode(request):
    try:
        node_name = request.POST.get('node_name')
        # 删除节点配置
        fname = NODE_CFG_FILES_DIR + node_name + '.cfg'
        if os.path.exists(fname):
            os.remove(fname)
        # 删除节点信息
        fname = NODE_INFO_FILES_DIR + node_name + '.info'
        if os.path.exists(fname):
            os.remove(fname)
        # 修改 nodesum
        node_num = 0
        if os.path.exists(NODESUM_FILE):
            configparser0 = ConfigParser.ConfigParser()
            configparser0.read(NODESUM_FILE)
            node_num = countNodes()
            configparser0.set('nodesum', 'num', str(node_num))
            configparser0.write(open(NODESUM_FILE,'w'))
        # 修改 openstack_deploy.conf
        if os.path.exists(OPENSTACK_DEPLOY_CONF):
            configparser = ConfigParser.ConfigParser()
            configparser.read(OPENSTACK_DEPLOY_CONF)
            
            # [node1SetInfo]
            section_name = node_name + 'SetInfo'
            removeSection(configparser, section_name)
                
            # [nodenum]
            setOption(configparser,'nodenum', 'nodesum', str(node_num))
            
            # [nodehostname]
            removeOption(configparser, 'nodehostname', 'node_name')
                
            # [nodeip]
            removeOption(configparser,'nodeip', node_name + NODE_DOMAIN_NAME + '_ip')
                
            # [componentinfo]
            node_role = getNodeRole(node_name[len('node'):])
            if 'Compute' in node_role:
                t_num = int(getOption(configparser,'componentinfo', 'computernum'))
                setOption(configparser,'componentinfo', 'computernum', str(t_num - 1))
                setOption(configparser, 'componentinfo', 'computer-neutronnum', str(t_num - 1))
                new_list = []
                for i in range(t_num):
                    t = getOption(configparser,'componentinfo','computernode' + str(i))
                    if t != node_name + NODE_DOMAIN_NAME:
                        new_list.append(t)
                for i in range(len(new_list)):
                    setOption(configparser,'componentinfo', 'computernode' + str(i), new_list[i])
                    setOption(configparser,'componentinfo', 'computer-neutronnode' + str(i), new_list[i])
            
            if 'Database' in node_role:
                t_num = int(getOption(configparser,'componentinfo', 'mysqlnum'))
                setOption(configparser, 'componentinfo', 'mysqlnum', str(t_num - 1))
                new_list = []
                for i in range(t_num):
                    t = getOption(configparser,'componentinfo','mysqlnode' + str(i))
                    if t != node_name + NODE_DOMAIN_NAME:
                        new_list.append(t)
                for i in range(len(new_list)):
                    setOption(configparser,'componentinfo', 'mysqlnode' + str(i), new_list[i])
                    
            if 'RabbitMQ' in node_role:
                t_num = int(getOption(configparser,'componentinfo', 'rabbitmqnum'))
                setOption(configparser,'componentinfo', 'rabbitmqnum', str(t_num - 1))
                new_list = []
                for i in range(t_num):
                    t = getOption(configparser,'componentinfo','rabbitmqnode' + str(i))
                    if t != node_name + NODE_DOMAIN_NAME:
                        new_list.append(t)
                for i in range(len(new_list)):
                    setOption(configparser, 'componentinfo', 'rabbitmqnode' + str(i), new_list[i])
            
            if 'Neutron' in node_role:
                t_num = int(getOption(configparser,'componentinfo', 'neutronnum'))
                setOption(configparser,'componentinfo', 'neutronnum', str(t_num - 1))
                new_list = []
                for i in range(t_num):
                    t = getOption(configparser,'componentinfo','neutronnode' + str(i))
                    if t != node_name + NODE_DOMAIN_NAME:
                        new_list.append(t)
                for i in range(len(new_list)):
                    setOption(configparser, 'componentinfo', 'neutronnode' + str(i), new_list[i])
                    
            if 'Storage-Cinder' in node_role:
                t_num = int(getOption(configparser,'componentinfo', 'cindernum'))
                setOption(configparser, 'componentinfo', 'cindernum', str(t_num - 1))
                new_list = []
                for i in range(t_num):
                    t = getOption(configparser,'componentinfo','cindernode' + str(i))
                    if t != node_name + NODE_DOMAIN_NAME:
                        new_list.append(t)
                for i in range(len(new_list)):
                    setOption(configparser, 'componentinfo', 'cindernode' + str(i), new_list[i])
                
            configparser.write(open(OPENSTACK_DEPLOY_CONF,'w'))
    except Exception as e:
        logger.error(traceback.format_exc())
        return HttpResponse('fail')
    return HttpResponse('success')

@login_required
def deleteEnv(request):
    doDeleteEnv()
    return HttpResponse('success')

def doDeleteEnv():
    try:
        # 删除相关文件
        if os.path.exists(NODE_INFO_FILES_DIR):
            shutil.rmtree(NODE_INFO_FILES_DIR)
        if os.path.exists(NODE_CFG_FILES_DIR):
            shutil.rmtree(NODE_CFG_FILES_DIR)
        if os.path.exists(OPENSTACK_DEPLOY_CONF):
            os.remove(OPENSTACK_DEPLOY_CONF)
        # 清空openstack日志
        clearOpenstackLog()
    except Exception as e:
        logger.error(traceback.format_exc())

def createOpenstackLog():
    if not os.path.exists(OPENSTACK_DEPLOY_LOG):
        os.mknod(OPENSTACK_DEPLOY_LOG)

def writeOpenstackLog(msg):
    createOpenstackLog()
    now_time = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(OPENSTACK_DEPLOY_LOG,'a') as f:
        f.write('%s-%s\n' % (now_time,msg))

def clearOpenstackLog():
    createOpenstackLog()
    with open(OPENSTACK_DEPLOY_LOG,'w') as f:
        f.truncate()

@login_required
def logshow(request):
    log_info = ''
    if os.path.exists(OPENSTACK_DEPLOY_LOG):
        with open(OPENSTACK_DEPLOY_LOG,'r') as f:
            log_info = f.read()
    return HttpResponse(log_info)

@login_required
def installStatus(request):
    statusDic = {}
    
    try:
        start_key = '##**##&'
        if os.path.exists(OPENSTACK_DEPLOY_LOG):
            log_lines = []
            with open(OPENSTACK_DEPLOY_LOG,'r') as f:
                log_lines = f.readlines()
            reversed_log_lines = list(reversed(log_lines)) # 反转
            for line in reversed_log_lines:
                if line and start_key in line:
                    status_info = line[line.find(start_key) + len(start_key):].replace('\n','')
                    status_info_arr = status_info.split(':')
                    if len(status_info_arr) >= 1 and status_info_arr[0] == 'deployover':
                        return HttpResponse(json.dumps({}))
                    elif len(status_info_arr) >= 3 and status_info_arr[0] == 'start': #【##**##&start:mysql:hostname】
                        statusDic[status_info_arr[2].replace(NODE_DOMAIN_NAME,'')] = '正在安装' + status_info_arr[1]
                        break
                    elif len(status_info_arr) >= 4 and status_info_arr[0] == 'end' \
                            and status_info_arr[3] == 'failed':#【##**##&end:hostname:mysql:success|fail】
                        statusDic[status_info_arr[1].replace(NODE_DOMAIN_NAME,'')] = status_info_arr[2] + '安装失败'
                        break
                    elif len(status_info_arr) >= 4 and status_info_arr[0] == 'end' \
                            and status_info_arr[3] == 'success':#【##**##&end:hostname:mysql:success|fail】
                        statusDic[status_info_arr[1].replace(NODE_DOMAIN_NAME,'')] = ''
                        break
                    
    except Exception as e:
        logger.error(traceback.format_exc())
        
    return HttpResponse(json.dumps(statusDic))
    

@login_required
def closeDhcp(request):
    return HttpResponse(stopDhcpService())

def stopDhcpService():
    try:
        writeOpenstackLog('*****close dhcp start*****')
        (s,o) = commands.getstatusoutput('systemctl stop dhcpd')
        if s == 0:
            writeOpenstackLog('*****close dhcp success*****')
            return 'success'
        else:
            logger.error('error to stopDhcpService:%s' % str(o))
            writeOpenstackLog('*****error to stopDhcpService: %s' % str(o))
    except Exception as e:
        logger.error(traceback.format_exc())
        writeOpenstackLog('*****error to stopDhcpService: %s' % traceback.format_exc())
    return 'fail'

def getDhcpAge():
    try:
        if os.path.exists(OPENSTACK_DEPLOY_CONF):
            configparser = ConfigParser.ConfigParser()
            configparser.read(OPENSTACK_DEPLOY_CONF)
            age = getOption(configparser, 'dhcp', 'dhcp_age')
            if age:
                return int(age)
    except Exception as e:
        logger.error(traceback.format_exc())
    return Paths().default_dhcp_age

@login_required
def openDhcp(request):
    writeOpenstackLog('*****open dhcp start*****')
    try:
        (s,o) = commands.getstatusoutput('systemctl start dhcpd')
        if s != 0:
            logger.error('error to openDhcp:%s' % str(o))
            writeOpenstackLog('*****open dhcp failed: %s' % str(o))
            return HttpResponse('fail')
        else:
            dhcp_age = getDhcpAge()
            th = threading.Timer(dhcp_age * 60, stopDhcpService)
            th.start()
    except Exception as e:
        err = traceback.format_exc()
        logger.error(err)
        writeOpenstackLog('*****open dhcp failed: %s' % str(err))
        return HttpResponse('fail')
    writeOpenstackLog('*****open dhcp success*****')
    return HttpResponse('success')

def getNodeRole(nodeIndex):
    try:
        nodeIndex = str(nodeIndex)
        configparser = ConfigParser.ConfigParser()
        configparser.read(OPENSTACK_DEPLOY_CONF)
        if configparser.has_section('componentinfo'):
            confList = configparser.items('componentinfo')
            roles = []
            for i in confList:
                if i[1] == 'node' + nodeIndex + NODE_DOMAIN_NAME:
                    keyword = i[0][0:0-len(nodeIndex)]
                    if 'Controller' not in roles and keyword in ['keystonenode','controller-glancenode',
                                                                 'controller-novanode',
                                                                'controller-neutronnode','controller-heatnode',
                                                                'controller-cindernode','controller-ceilometernode',
                                                                'controller-horizonnode','nfsnode']:
                        roles.append('Controller')
                    elif 'Compute' not in roles and keyword in ['computernode','computer-neutronnode']:
                        roles.append('Compute')
                    elif 'Database' not in roles and keyword == 'mysqlnode':
                        roles.append('Database')
                    elif 'RabbitMQ' not in roles and keyword == 'rabbitmqnode':
                        roles.append('RabbitMQ')
                    elif 'Neutron' not in roles and keyword == 'neutronnode':
                        roles.append('Neutron')
                    elif 'Storage-Cinder' not in roles and keyword == 'cindernode':
                        roles.append('Storage-Cinder')

            return ','.join(roles)
            
    except Exception as e:
        logger.error(traceback.format_exc())
    return ''


@login_required
def findnodes(request):
    res = []
    try:
        p=subprocess.Popen("/usr/share/deployboard/deployboard.py \"Request Hardware Information\"", shell=True)  
        
        time.sleep(5)
        
        p.kill()
        
        nodenum = 0
        
        if os.path.exists(NODESUM_FILE):
            configparser2 = ConfigParser.ConfigParser()
            configparser2.read(NODESUM_FILE)
            nodenum = countNodes() # 获取节点个数
            
        configparser = ConfigParser.ConfigParser()
        configparser.read(OPENSTACK_DEPLOY_CONF)
        
        #[nodenum]
        setOption(configparser, 'nodenum', 'nodesum', str(nodenum))
        
        #[nodehostname][nodeip]
        exists_nodes = []
        if configparser.has_section('nodehostname'):
            exists_nodes = [n[0] for n in configparser.items('nodehostname')]
        clearSection(configparser, 'nodehostname')
        clearSection(configparser, 'nodeip')
        
        setOption(configparser, 'nodehostname', 'node0', 'master.server.com' )
        localip = getLocalIp()
    
        setOption(configparser, 'nodeip', 'master.server.com_ip', localip)
        num = 0
        i = 0
        deploystatus = getOption(configparser, 'deployinfo', 'deploystatus')
        while num < int(nodenum):
            nodename = 'node' + str(i + 1)
            if os.path.exists(NODE_INFO_FILES_DIR + nodename + '.info'):
                with open(NODE_INFO_FILES_DIR + nodename + '.info','r') as f:
                    nodeinfo = json.loads(f.read())
                    nodeip = nodeinfo.get('ipaddress')
                    setOption(configparser, 'nodeip', nodename + NODE_DOMAIN_NAME + '_ip', nodeip)
                setOption(configparser, 'nodehostname', nodename, nodename + NODE_DOMAIN_NAME)
                
                if deploystatus and deploystatus != 'nodeploy':
                    if nodename not in exists_nodes:
                        setOption(configparser, 'newcomputernodes', nodename, nodename + NODE_DOMAIN_NAME)
                num += 1
            i += 1
        configparser.write(open(OPENSTACK_DEPLOY_CONF,'w'))
        
        res = getNodeList('1')
    except Exception as e:
        logger.error(traceback.format_exc())
    return HttpResponse(json.dumps(res))

@login_required
def listnodes(request, targetPage = '1'):
    return HttpResponse(json.dumps( getNodeList(targetPage)))

def list_new_computer_nodes():
	if os.path.exists(OPENSTACK_DEPLOY_CONF):
		cfgparser = ConfigParser.ConfigParser()
		cfgparser.read(OPENSTACK_DEPLOY_CONF)
		if cfgparser.has_section('newcomputernodes'):
			items = cfgparser.items('newcomputernodes')
			return [i[0] for i in items]
	return []

def getNodeList(targetPage = '1'):
    targetPage = int(targetPage)
    nodes = []
    nodenum = 0
    args = {'error':''}
    try:
        if os.path.exists(NODESUM_FILE):
            configparser = ConfigParser.ConfigParser()
            configparser.read(OPENSTACK_DEPLOY_CONF)
            configparser2 = ConfigParser.ConfigParser()
            configparser2.read(NODESUM_FILE)
            nodenum = countNodes() # 获取节点个数
            index = 0
            num = 0
            new_computer_nodes = list_new_computer_nodes()
            deploystatus = getOption(configparser, 'deployinfo', 'deploystatus')
            while num < int(nodenum):
                info_file = NODE_INFO_FILES_DIR + 'node' + str(index) + '.info'
                if os.path.exists(info_file):
                    with open(info_file,'r') as f:
                        info = json.loads(f.read())
                        dic = {}
                        dic['nodename'] = 'node' + str(index)
                        if deploystatus and deploystatus != 'nodeploy' and dic['nodename'] in new_computer_nodes:
                        	dic['is_new'] = '1'
                        dic['macaddress'] = info.get('macaddress')
                        dic['physicalprocessorcount'] = info.get('physicalprocessorcount')
                        dic['processorcount'] = info.get('processorcount')
                        dic['ram'] = info.get('memorysize')
                        dic['roles'] = getNodeRole(index)
                        hdd = 0
                        partitions = info.get('partitions')
                        for p_key in partitions:
                            hdd += int(partitions.get(p_key).get('size'))
                        hdd = hdd / 1024 / 1024 / 2
                        dic['hdd'] = str(hdd) + 'GB'
                        nodes.append(dic)
                    num = num + 1
                index = index + 1
                
    except Exception as e:
        logger.error(traceback.format_exc())
        args['error'] = 'READ_ERROR'
        return args

    args = {'nodenum':str(nodenum),'nodes':json.dumps(nodes)}
    return args



@login_required
def fornodecfg(request,nodename):
    dic = {}
    try:
        node_role = request.POST.get('node_role')
        need_datanet = False # 是否需要数据网卡
        if node_role :
            for role in NODETYPE_NETTYPE_NESSESARY:
                if role in node_role and 'datanet' in NODETYPE_NETTYPE_NESSESARY[role]:
                    need_datanet = True
                
        info_file = NODE_INFO_FILES_DIR + nodename + '.info'
        if os.path.exists(info_file):
            configparser = ConfigParser.ConfigParser()
            configparser.read(OPENSTACK_DEPLOY_CONF)
            
            dic['net_type'] = getOption(configparser, 'networkinfo', 'networktype')

            section_name = nodename + 'SetInfo'

            managenetcardname = getOption(configparser, section_name, 'managenetcardname')
            storagenetcardname = getOption(configparser, section_name, 'storagenetcardname')
            datanetcardname = getOption(configparser, section_name, 'datanetcardname')
            outernetcardname = getOption(configparser, section_name, 'outernetcardname')
                
            with open(info_file,'r') as f:
                info = json.loads(f.read())
                dic['net'] = []
                dic['disk'] = []
                has_datanet = False # 是否存在数据网卡
                for key in info:
                    managenetcardmac = info.get('macaddress')
                    if key.startswith('macaddress_'):
                        card = key.replace('macaddress_','')
                        netTypes = ''
                        if info.get(key) == managenetcardmac:
                            netTypes = 'managenet'
                        if storagenetcardname and storagenetcardname == card:
                            netTypes += ',' if netTypes else ''
                            netTypes += 'storagenet'
                        if datanetcardname and datanetcardname == card:
                            netTypes += ',' if netTypes else ''
                            netTypes += 'datanet'
                            has_datanet = True
                        if outernetcardname and outernetcardname == card:
                            netTypes += ',' if netTypes else ''
                            netTypes += 'outernet'
                        
                        dic['net'].append({'name':card,'mac':info.get(key) or '',
                                           'netType':netTypes,
                                           'ip':info.get('ipaddress_'+card) 
                                                    or getOption(configparser, section_name, 'ipaddress_'+card) ,
                                           'netmask':info.get('netmask_'+card) 
                                                    or getOption(configparser, section_name, 'netmask_'+card) ,
                                           'dns':''})
                    if key == 'partitions':
                        partitions = info.get('partitions')
                        for p in partitions:
                            d = partitions.get(p)
                            d['name'] = p
                            d['size'] = str(round(int(d['size']) / 1024.0 / 1024.0,2)) + ' GB'
                                
                            dic['disk'].append(d)
                # 对于gre和vxlan网络，如果需要datanet网卡但还没设置，默认把managenet网卡当成datanet网卡
                if need_datanet and not has_datanet and dic['net_type'] in ['gre','vxlan']: 
                    for dd in dic['net']:
                        if 'managenet' in dd.get('netType'):
                            dd['netType'] += ',datanet'
            for di in dic['disk']:
                diskType = getOption(configparser,section_name, di.get('name'))
                di['diskType'] = diskType
        dic['net'].sort(key = lambda e:e['name'])
        dic['disk'].sort(key = lambda e:e['name'])
    except Exception as e:
        logger.error(traceback.format_exc())
    return HttpResponse(json.dumps(dic))

@login_required
def create(request):
    writeOpenstackLog('*****create openstack environment start*****')
    try:
        colud_evn_name = request.POST.get('colud_evn_name') #云环境名称
#         deploy_mode = request.POST.get('deploy_mode') #部署模式
#         takeover_platform = request.POST.get('takeover_platform') #接管平台
        network = request.POST.get('network') #数据网络
        
        cidr = request.POST.get('cidr') #管理网络-CIDR
        ip_range_min = request.POST.get('ip_range_min') #管理网络-开始IP
        ip_range_max = request.POST.get('ip_range_max') #管理网络-结束IP
        gateway = request.POST.get('gateway') #管理网络-网关
        dns = request.POST.get('dns1') #管理网络-DNS
        
        storage_vminstance = request.POST.get('storage_vminstance') #存储-虚机实例
        storage_vmimage = request.POST.get('storage_vmimage') #存储-虚机镜像
        storage_userdisk = request.POST.get('storage_userdisk') #存储-用户磁盘

        if not os.path.exists(OPENSTACK_DEPLOY_CONF):
            os.mknod(OPENSTACK_DEPLOY_CONF)
    
        configparser = ConfigParser.ConfigParser()
        configparser.read(OPENSTACK_DEPLOY_CONF)
        
        #云环境名称
        setOption(configparser, 'cenvironmentname', 'cenvironmentname', colud_evn_name)

        # DHCP持续时间，默认10分钟
        setOption(configparser, 'dhcp', 'dhcp_age', str(Paths().default_dhcp_age))

        #[componentorder]
        setOption(configparser, 'componentorder', 'componentnum', '16')
        setOption(configparser,'componentorder', 'comorder0', 'mysql')
        setOption(configparser,'componentorder', 'comorder1', 'rabbitmq')
        setOption(configparser,'componentorder', 'comorder2', 'nfs')
        setOption(configparser,'componentorder', 'comorder3', 'keystone')
        setOption(configparser,'componentorder', 'comorder4', 'controller-glance')
        setOption(configparser,'componentorder', 'comorder5', 'controller-nova')
        setOption(configparser,'componentorder', 'comorder6', 'controller-neutron')
        setOption(configparser,'componentorder', 'comorder7', 'controller-heat')
        setOption(configparser,'componentorder', 'comorder8', 'controller-cinder')
        setOption(configparser,'componentorder', 'comorder9', 'controller-horizon')
        setOption(configparser,'componentorder', 'comorder10', 'mongodb')
        setOption(configparser,'componentorder', 'comorder11', 'controller-ceilometer')
        setOption(configparser,'componentorder', 'comorder12', 'neutron')
        setOption(configparser,'componentorder', 'comorder13', 'cinder')
        setOption(configparser,'componentorder', 'comorder14', 'computer')
        setOption(configparser,'componentorder', 'comorder15', 'ceilometer-snmp')
	

        #[networkinfo]
        setOption(configparser, 'networkinfo', 'networktype', network)
        #[storagetype]
        setOption(configparser, 'storagetype', 'vminstance', storage_vminstance)
        setOption(configparser, 'storagetype', 'vmimage', storage_vmimage)
        setOption(configparser, 'storagetype', 'userdisk', storage_userdisk)
        #[nodeloginfo]
        setOption(configparser, 'nodeloginfo', 'nodeusername', 'root')
        setOption(configparser, 'nodeloginfo', 'nodepasswd', 'rootroot')
        
        configparser.write(open(OPENSTACK_DEPLOY_CONF,'w'))
        
        # 修改/etc/config
        local_ip = getLocalIp()
            
    except Exception as e:
        doDeleteEnv()
        err = traceback.format_exc()
        logger.error(err)
        writeOpenstackLog('*****create openstack environment failed, error in create : %s' % str(err))
        return HttpResponse('error')
    writeOpenstackLog('*****create openstack environment success*****')
    return HttpResponse('success')

@login_required
def deployChange(request):
    writeOpenstackLog('*****openstack deploy start*****')
    try:
        if not os.path.exists(OPENSTACK_DEPLOY_CONF):
            os.mknod(OPENSTACK_DEPLOY_CONF)

        configparser = ConfigParser.ConfigParser()
        configparser.read(OPENSTACK_DEPLOY_CONF)
        # 判断是否正在部署中
        if getOption(configparser, 'deployinfo', 'deploystatus') == 'deploying':
            return HttpResponse('deploying')
        # 判断部署网络是否已填写
        networktype = getOption(configparser, 'networkinfo', 'networktype')
        if networktype == 'gre':
            if not getOption(configparser, 'network', 'gre_cidr'):
                return HttpResponse('netinfoloss_gre')
        elif networktype == 'vlan':
            if not getOption(configparser, 'network', 'vlan_cidr'):
                return HttpResponse('netinfoloss_vlan')
        elif networktype == 'vxlan':
            if not getOption(configparser, 'network', 'vxlan_cidr'):
                return HttpResponse('netinfoloss_vxlan')
        
        src_nodeConfig = json.loads(request.POST.get('nodeConfig'))

        nodeConfig = {}
        # 验证一次节点是否存在，避免参数传错导致的错误
        for node in src_nodeConfig:
            if os.path.exists(NODE_INFO_FILES_DIR + node + '.info'):
                nodeConfig[node] = src_nodeConfig.get(node)

        ControllerList = []
        ComputeList = []
        DatabaseList = []
        RabbitMQList = []
        NeutronList = []
        CinderList = []
        
        for node in nodeConfig:
            if 'Controller' in nodeConfig[node]:
                ControllerList.append(node)
            if 'Compute' in nodeConfig[node]:
                ComputeList.append(node)
            if 'Database' in nodeConfig[node]:
                DatabaseList.append(node)
            if 'RabbitMQ' in nodeConfig[node]:
                RabbitMQList.append(node)
            if 'Neutron' in nodeConfig[node]:
                NeutronList.append(node)
            if 'Storage-Cinder' in nodeConfig[node]:
                CinderList.append(node)
        
        ControllerList.sort()
        ComputeList.sort()
        DatabaseList.sort()
        RabbitMQList.sort()
        NeutronList.sort()
        CinderList.sort()

        # 写文件 openstack_deploy.conf
        
        # [componentinfo]
        clearSection(configparser, 'componentinfo')
            
        setOption(configparser, 'componentinfo', 'mysqlnum', len(DatabaseList))
        for i in range(len(DatabaseList)):
            setOption(configparser, 'componentinfo', 'mysqlnode'+str(i), DatabaseList[i]+NODE_DOMAIN_NAME)
            
        setOption(configparser, 'componentinfo', 'rabbitmqnum', len(RabbitMQList))
        for i in range(len(RabbitMQList)):
            setOption(configparser, 'componentinfo', 'rabbitmqnode'+str(i), RabbitMQList[i]+NODE_DOMAIN_NAME)
        
        setOption(configparser, 'componentinfo', 'keystonenum', len(ControllerList))
        for i in range(len(ControllerList)):
            setOption(configparser, 'componentinfo', 'keystonenode'+str(i), ControllerList[i]+NODE_DOMAIN_NAME)
        setOption(configparser, 'componentinfo', 'controller-glancenum', len(ControllerList))
        for i in range(len(ControllerList)):
            setOption(configparser, 'componentinfo', 'controller-glancenode'+str(i), 
                      ControllerList[i]+NODE_DOMAIN_NAME)
        setOption(configparser, 'componentinfo', 'controller-novanum', len(ControllerList))
        for i in range(len(ControllerList)):
            setOption(configparser, 'componentinfo', 'controller-novanode'+str(i), ControllerList[i]+NODE_DOMAIN_NAME)
        setOption(configparser, 'componentinfo', 'controller-neutronnum', len(ControllerList))
        for i in range(len(ControllerList)):
            setOption(configparser, 'componentinfo', 'controller-neutronnode'+str(i), 
                      ControllerList[i]+NODE_DOMAIN_NAME)
        setOption(configparser, 'componentinfo', 'controller-heatnum', len(ControllerList))
        for i in range(len(ControllerList)):
            setOption(configparser, 'componentinfo', 'controller-heatnode'+str(i), ControllerList[i]+NODE_DOMAIN_NAME)
        setOption(configparser, 'componentinfo', 'controller-cindernum', len(ControllerList))
        for i in range(len(ControllerList)):
            setOption(configparser, 'componentinfo', 'controller-cindernode'+str(i), 
                      ControllerList[i]+NODE_DOMAIN_NAME)
        setOption(configparser, 'componentinfo', 'mongodbnum', len(ControllerList))
        for i in range(len(ControllerList)):
            setOption(configparser, 'componentinfo', 'mongodbnode'+str(i),
                      ControllerList[i]+NODE_DOMAIN_NAME)
        setOption(configparser, 'componentinfo', 'controller-ceilometernum', len(ControllerList))
        for i in range(len(ControllerList)):
            setOption(configparser, 'componentinfo', 'controller-ceilometernode'+str(i), 
                      ControllerList[i]+NODE_DOMAIN_NAME)
        setOption(configparser, 'componentinfo', 'controller-horizonnum', len(ControllerList))
        for i in range(len(ControllerList)):
            setOption(configparser, 'componentinfo', 'controller-horizonnode'+str(i), 
                      ControllerList[i]+NODE_DOMAIN_NAME)
        setOption(configparser, 'componentinfo', 'nfsnum', len(ControllerList))
        for i in range(len(ControllerList)):
            setOption(configparser, 'componentinfo', 'nfsnode'+str(i), ControllerList[i]+NODE_DOMAIN_NAME)
            
        setOption(configparser, 'componentinfo', 'cindernum', len(CinderList))
        for i in range(len(CinderList)):
            setOption(configparser, 'componentinfo', 'cindernode'+str(i), CinderList[i]+NODE_DOMAIN_NAME)
        
        setOption(configparser, 'componentinfo', 'neutronnum', len(NeutronList))
        for i in range(len(NeutronList)):
            setOption(configparser, 'componentinfo', 'neutronnode'+str(i), NeutronList[i]+NODE_DOMAIN_NAME)
        
        setOption(configparser, 'componentinfo', 'computernum', len(ComputeList))
        for i in range(len(ComputeList)):
            setOption(configparser, 'componentinfo', 'computernode'+str(i), ComputeList[i]+NODE_DOMAIN_NAME)
        setOption(configparser, 'componentinfo', 'computer-neutronnum', len(ComputeList))
        for i in range(len(ComputeList)):
            setOption(configparser, 'componentinfo', 'computer-neutronnode'+str(i), ComputeList[i]+NODE_DOMAIN_NAME)
        setOption(configparser, 'componentinfo', 'ceilometer-snmpnum', len(ComputeList))
        for i in range(len(ComputeList)):
            setOption(configparser, 'componentinfo', 'ceilometer-snmpnode'+str(i), ComputeList[i]+NODE_DOMAIN_NAME)	
	
#         clearSection(configparser, 'newcomputernodes') # 清空新节点列表
	
        configparser.write(open(OPENSTACK_DEPLOY_CONF,'w'))
        
        compute_node_list = ''
        for i in ComputeList:
            if compute_node_list:
                compute_node_list += ' '
            compute_node_list += getOption(configparser, 'nodeip', i + NODE_DOMAIN_NAME + '_ip') 
        
        # 写文件 node.cfg
        for node in nodeConfig:
            if not os.path.exists(NODE_CFG_FILES_DIR):
                os.makedirs(NODE_CFG_FILES_DIR, 0755)
            cfg_file = NODE_CFG_FILES_DIR + node + '.cfg'
            node_info_file = NODE_INFO_FILES_DIR + node + '.info'
            if not os.path.exists(node_info_file):
                continue
            lines = []
            node_info = {}
            with open(node_info_file,'r') as f:
                node_info = json.loads(f.read())
            manage_ip = node_info.get('ipaddress')
            for key in node_info:
                if key.startswith('ipaddress_') and node_info.get(key) == manage_ip:
                    manage_networkcard_name = key.replace('ipaddress_','')
            manage_networkcard_ip = node_info.get('ipaddress_' + manage_networkcard_name)
            manage_networkcard_mask = node_info.get('netmask_' + manage_networkcard_name)
            lines.append('MANAGE_NETWORKCARD_NAME='+manage_networkcard_name)
            manage_network_segment = getOption(configparser, 'network', 'manage_cidr')
            lines.append('MANAGE_NETWORK_SEGMENT=' + manage_network_segment)
            
            data_networkcard_ip = ''
            data_networkcard_mask = ''
            data_networkcard_dns = ''
            data_networkcard_name = getOption(configparser,node + 'SetInfo', 'datanetcardname')
            if data_networkcard_name:
                data_networkcard_ip = getOption(configparser, node + 'SetInfo', 'ipaddress_' + data_networkcard_name)
                data_networkcard_mask = getOption(configparser, node + 'SetInfo', 'netmask_' + data_networkcard_name)
                data_networkcard_dns = getOption(configparser, node + 'SetInfo', 'dns_' + data_networkcard_name)
            lines.append('DATA_NETWORKCARD_NAME=' + data_networkcard_name)
            
            
            external_networkcard_name = getOption(configparser, node + 'SetInfo', 'outernetcardname')
            lines.append('EXTERNAL_NETWORKCARD_NAME='+external_networkcard_name)
            
            store_networkcard_name = getOption(configparser,node + 'SetInfo', 'storagenetcardname')
            
            
            lines.append('STORE_NETWORKCARD_NAME=' + store_networkcard_name)
            controller_node_hostname = getOption(configparser,'componentinfo','keystonenode0')
            controller_node_ip = ''
            if controller_node_hostname:
                controller_node_ip = getOption(configparser, 'nodeip',controller_node_hostname + '_ip')
            lines.append('CONTROLLER_NODE_IP=' + controller_node_ip)
            lines.append('CONTROLLER_NODE_HOSTNAME=' + controller_node_hostname.replace(NODE_DOMAIN_NAME,''))
            network_node_hostname = getOption(configparser,'componentinfo','neutronnode0')
            network_node_ip = ''
            if network_node_hostname:
                network_node_ip = getOption(configparser,'nodeip',network_node_hostname + '_ip')
            lines.append('NETWORK_NODE_IP=' + network_node_ip)
            lines.append('NETWORK_NODE_HOSTNAME=' + network_node_hostname.replace(NODE_DOMAIN_NAME, ''))
            mariadb_node_ip = ''
            mariadb_node_hostname = getOption(configparser,'componentinfo', 'mysqlnode0')
            if mariadb_node_hostname:
                mariadb_node_ip = getOption(configparser,'nodeip',mariadb_node_hostname + '_ip')
            lines.append('MARIADB_NODE_IP=' + mariadb_node_ip)
            lines.append('MARIADB_NODE_HOSTNAME=' + mariadb_node_hostname.replace(NODE_DOMAIN_NAME, ''))

            lines.append('MARIADB_USER_PASS=123456')
            lines.append('NFS_NODE_HOSTNAME='+controller_node_hostname.replace(NODE_DOMAIN_NAME, ''))
            lines.append('NFS_NODE_IP='+controller_node_ip)
            rabbitmq_node_ip = ''
            rabbitmq_node_hostname = getOption(configparser,'componentinfo', 'rabbitmqnode0')
            if rabbitmq_node_hostname:
                rabbitmq_node_ip = getOption(configparser, 'nodeip',rabbitmq_node_hostname + '_ip')
            lines.append('RABBITMQ_NODE_IP=' + rabbitmq_node_ip)
            lines.append('RABBITMQ_NODE_HOSTNAME=' + rabbitmq_node_hostname.replace(NODE_DOMAIN_NAME, ''))
            lines.append('RABBITMQ_USER_NAME=admin')
            lines.append('RABBITMQ_USER_PASS=admin')
            lines.append('KEYSTON_DB_PASS=keystoneDB')
            lines.append('ADMIN_USER_TOKEN=openstack_admin_token')
            lines.append('ADMIN_USER_PASS=admin')
            lines.append('ADMIN_MAIL=')
            lines.append('DEMO_USER_PASS=demo')
            lines.append('DEMO_MAIL=xxx')
            lines.append('GLANCE_USER_PASS=glance')
            lines.append('GLANCE_DB_PASS=glanceDB')
            lines.append('GLANCE_STORE_TYPE=' + getOption(configparser, 'storagetype', 'vmimage'))
            lines.append('GLANCE_LOCAL_FILE_STORE_DIR=/var/lib/glance/images/')
            lines.append('NOVA_DB_PASS=novaDB')
            lines.append('NOVA_USER_PASS=nova')
            lines.append('COMPUTE_VM_STORE_TYPE=' + getOption(configparser, 'storagetype', 'vminstance'))
            lines.append('NEUTRON_DB_PASS=neutronDB')
            lines.append('NEUTRON_USER_PASS=neutron')
            network_type = getOption(configparser, 'networkinfo', 'networktype')
            lines.append('NETWORK_TYPE=' + network_type)
            manage_cidr = getOption(configparser, 'network', 'manage_cidr')
            data_cidr = ''
            if network_type == 'gre':
                data_cidr = getOption(configparser, 'network', 'gre_cidr')
            elif network_type == 'vlan':
                data_cidr = getOption(configparser, 'network', 'vlan_cidr')
            elif network_type == 'vxlan':
                data_cidr = getOption(configparser, 'network', 'vxlan_cidr')
            manage_data_net_inone = 'false'
            if manage_cidr == data_cidr:
                manage_data_net_inone = 'true'
            lines.append('MANAGE_DATA_NET_INONE=' + manage_data_net_inone)
            lines.append('VLAN_ID_BEGIN_VALUE=' + getOption(configparser, 'network', 'vlan_ipstart'))
            lines.append('VLAN_ID_END_VALUE=' + getOption(configparser, 'network', 'vlan_ipend'))
            lines.append('VXLAN_ID_BEGIN_VALUE=' + getOption(configparser, 'network', 'vxlan_ipstart'))
            lines.append('VXLAN_ID_END_VALUE=' + getOption(configparser, 'network', 'vxlan_ipend'))
            
            network_node_vlan_ip = ''
            network_node_vlan_netmask = ''
            network_node_vlan_dns = ''
            if network_type == 'vlan':
                network_node_vlan_ip = data_networkcard_ip
                network_node_vlan_netmask = data_networkcard_mask
                network_node_vlan_dns = data_networkcard_dns
            lines.append('NETWORK_NODE_VLAN_IP=' + network_node_vlan_ip)
            lines.append('NETWORK_NODE_VLAN_NETMASK=' + network_node_vlan_netmask)
            lines.append('NETWORK_NODE_VLAN_DNS=114.114.114.114')
            network_node_tunnel_ip = ''
            network_node_tunnel_netmask = ''
            if network_type in ['gre','vxlan']:
                network_node_tunnel_ip = data_networkcard_ip
                network_node_tunnel_netmask = data_networkcard_mask
            lines.append('NETWORK_NODE_TUNNEL_IP=' + network_node_tunnel_ip)
            lines.append('NETWORK_NODE_TUNNEL_NETMASK=' + network_node_tunnel_netmask)
            lines.append('META_PWD=meta')
            lines.append('CINDER_DB_PASS=cinderDB')
            lines.append('CINDER_USER_PASS=cinder')
            lines.append('SWIFT_NODE_IP=')
            lines.append('SWIFT_USER_PASS=xxx')
            lines.append('HEAT_DB_PASS=heatDB')
            lines.append('HEAT_USER_PASS=heat')
            lines.append('MONGODB_DATABASE_IP=' + controller_node_ip)
            lines.append('MONGODB_DATABASE_HOSTNAME=' + controller_node_hostname.replace(NODE_DOMAIN_NAME,''))
            lines.append('CEILOMETER_DB_PASS=ceilometerDB')
            lines.append('CEILOMETER_USER_PASS=ceilometer')
            lines.append('TROVE_USER_PASS=xxx')
            lines.append('TROVE_DB_PASS=xxx')
            
            lines.append('DASHBOARD_HOST=' + mariadb_node_ip)
            lines.append('DASHBOARD_NAME=dashboarddb')
            lines.append('DASHBOARD_USER=dashboard')
            lines.append('DASHBOARD_PASS=123456')
            lines.append('DASHBOARD_PORT=3306')
            

            lines.append('COMPUTE_NODE_LIST="' + compute_node_list + '"') 
            
            content = '\n'.join(lines)
            
            with open(cfg_file,'w') as f:
                f.write(content)
            
        # ##############################
        cmds = ['/usr/share/deployboard/changeNodesHost.py >> %s' % OPENSTACK_DEPLOY_LOG,
                5]
        for c in cmds:
            if type(c) == type(1):
                time.sleep(c)
            else:
                (s,o) = commands.getstatusoutput(c)
                if s != 0:
                    logger.error('error to execute command [%s]: %s' % (c,str(o)))
                    return HttpResponse('fail')

        if getOption(configparser, 'deployinfo', 'deploystatus') == 'nodeploy':
            p = subprocess.Popen('/usr/share/deployboard/openStkDeployment.py >> %s' % OPENSTACK_DEPLOY_LOG,shell=True)
        else:
            p = subprocess.Popen('/usr/share/deployboard/deployAddNodes.py >> %s' % OPENSTACK_DEPLOY_LOG,shell=True)
        
        controller_hostname = getOption(configparser, 'componentinfo', 'keystonenode0')
        controller_ip = ''
        if controller_hostname:
            controller_ip = getOption(configparser, 'nodeip', controller_hostname + '_ip')
        return HttpResponse('success,' + controller_ip)
                    
    except Exception as e:
        err_msg = traceback.format_exc()
        logger.error(err_msg)
        writeOpenstackLog('*****openstack deploy failed, error in deployChange : %s' % err_msg)
        return HttpResponse('fail')
    writeOpenstackLog('*****openstack deploy success*****')
    return HttpResponse('success')

@login_required
def configNode(request):
    try:
        nodeName = request.POST.get('node_name')
        netDic = json.loads( request.POST.get('net'))
        diskDic = json.loads(request.POST.get('disk'))

        if not os.path.exists(OPENSTACK_DEPLOY_CONF):
            os.mknod(OPENSTACK_DEPLOY_CONF)
    
        configparser = ConfigParser.ConfigParser()
        configparser.read(OPENSTACK_DEPLOY_CONF)
        
        managenetcardname = ''
        managenetcardmac = ''
        storagenetcardname = ''
        storagenetcardmac = ''
        datanetcardname = ''
        datanetcardmac = ''
        outernetcardname = ''
        outernetcardmac = ''
        
        for k in netDic:
            if 'managenet' in  netDic[k].get('netType'):
                managenetcardname = k
                managenetcardmac = netDic[k].get('mac')
            if 'storagenet' in  netDic[k].get('netType'):
                storagenetcardname = k
                storagenetcardmac = netDic[k].get('mac')
            if 'datanet' in  netDic[k].get('netType'):
                datanetcardname = k
                datanetcardmac = netDic[k].get('mac')
            if 'outernet' in  netDic[k].get('netType'):
                outernetcardname = k
                outernetcardmac = netDic[k].get('mac')
        section_name = nodeName + 'SetInfo'
        
        setOption(configparser, section_name, 'managenetcardname', managenetcardname)
        setOption(configparser, section_name, 'managenetcardmac', managenetcardmac)
        setOption(configparser, section_name, 'storagenetcardname', storagenetcardname)
        setOption(configparser, section_name, 'storagenetcardmac', storagenetcardmac)
        setOption(configparser, section_name, 'datanetcardname', datanetcardname)
        setOption(configparser, section_name, 'datanetcardmac', datanetcardmac)
        setOption(configparser, section_name, 'outernetcardname', outernetcardname)
        setOption(configparser, section_name, 'outernetcardmac', outernetcardmac)
        for n in netDic:
            info = netDic.get(n)
            setOption(configparser, section_name, 'ipaddress_' + n, info.get('ip') or '')
            setOption(configparser, section_name, 'netmask_' + n, info.get('netmask') or '')
            setOption(configparser, section_name, 'dns_' + n, info.get('dns') or '')
        
        nodeIp = getOption(configparser, 'nodeip', nodeName + NODE_DOMAIN_NAME + '_ip')
        for k in diskDic:
            old = getOption(configparser, section_name, k)
            if old != 'cinder' and diskDic.get(k) == 'cinder': # 为提供cinder卷服务的节点增加提供存储的硬盘时
                execRemoteCommond(nodeIp,'expand-cinder-store /dev/%s >> %s' % (k,OPENSTACK_DEPLOY_LOG))
            elif old == 'cinder' and not diskDic.get(k): # 为提供cinder卷服务的节点减少提供存储的硬盘时
                execRemoteCommond(nodeIp,'reduce-cinder-store /dev/%s >> %s' % (k,OPENSTACK_DEPLOY_LOG))
            elif old != 'nfs' and diskDic.get(k) == 'nfs': # 当提供nfs的节点增加硬盘时，来增加nfs节点的存储空间
                execRemoteCommond(nodeIp,'expand-nfs-store /dev/%s >> %s' % (k,OPENSTACK_DEPLOY_LOG))
            setOption(configparser, section_name, k, diskDic.get(k))
            
        configparser.write(open(OPENSTACK_DEPLOY_CONF,'w'))
    except Exception as e:
        logger.error(traceback.format_exc())
        return HttpResponse('error')
    return HttpResponse('success')

def execRemoteCommond(ip,commond):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ip,22,conf.get("nodeloginfo","nodeusername"),conf.get("nodeloginfo","nodepasswd"))
        stdin, stdout, stderr = ssh.exec_command(commond)
        ssh.close()
    except Exception as e:
        logger.error(traceback.format_exc())

@login_required
def netConfig(request):
    try:
        form_data = json.loads( request.POST.get('form_data'))

        configparser = ConfigParser.ConfigParser()
        configparser.read(OPENSTACK_DEPLOY_CONF)
        clearSection(configparser, 'network')
        for k in form_data:
            if k in ['manage_dns','storage_dns'] and type(form_data[k]) == type([]):
                for i in range(len( form_data[k])):
                    if form_data[k][i]:
                        setOption(configparser, 'network', k + str(i+1), form_data[k][i])
            else:
                setOption(configparser, 'network', k, form_data[k])
        configparser.write(open(OPENSTACK_DEPLOY_CONF,'w'))

        # 修改/etc/deploy_node_config
        if not os.path.exists(Paths().deploy_node_config):
            os.mknod(Paths().deploy_node_config)
        lines = []
        lines.append('THIS_HOST_IP="%s"\n' % getLocalIp())
        lines.append('THIS_NETWORK_SEGMENT="%s"\n' % form_data['manage_cidr'].split('/')[0])
        lines.append('DHCP_BEGIN_RANGE="%s"\n' % form_data['manage_ipstart'])
        lines.append('DHCP_END_RANGE="%s"\n' % form_data['manage_ipend'])
        lines.append('THIS_HOST_GATEWAY="%s"\n' % form_data['manage_gateway'])
        dns = ''
        if type(form_data['manage_dns']) == type([]):
            dns = form_data['manage_dns'][0]
        else:
            dns = form_data['manage_dns']
        lines.append('THIS_HOST_DNS="%s"\n' % dns)
        lines.append('THIS_HOST_NETMASK="%s"\n' % exchange_prefix(form_data['manage_cidr'].split('/')[1]))
        with open(Paths().deploy_node_config,'r') as f:
            for line in f.readlines():
                if 'THIS_HOST_IP' in line \
                        or 'THIS_NETWORK_SEGMENT' in line \
                        or 'DHCP_BEGIN_RANGE' in line \
                        or 'DHCP_END_RANGE' in line \
                        or 'THIS_HOST_GATEWAY' in line \
                        or 'THIS_HOST_DNS' in line \
                        or 'THIS_HOST_NETMASK' in line:
                    pass
                else:
                    lines.append(line)
        with open(Paths().deploy_node_config,'w') as f:
            f.writelines(lines)
    except Exception as e:
        logger.error(traceback.format_exc())
        return HttpResponse('error')
    return HttpResponse('success')

@login_required
def forNetConfig(request):
    net_data = {}
    try:
        configparser = ConfigParser.ConfigParser()
        configparser.read(OPENSTACK_DEPLOY_CONF)
        networktype = getOption(configparser, 'networkinfo', 'networktype')
        net_data['networktype'] = networktype
        if configparser.has_section('network'):
            items = configparser.items('network')
            for i in items:
                net_data[i[0]] = i[1]
        
        net_data['manage_cidr'] = ''
        net_data['manage_ipstart'] = ''
        net_data['manage_ipend'] = ''
        net_data['manage_gateway'] = ''
        net_data['manage_dns'] = ''
        def pickInfo(line):
            return line.split('=')[1].replace('\n','').replace('"','')
        if os.path.exists(Paths().deploy_node_config):
            segment = ''
            mask = ''
            with open(Paths().deploy_node_config,'r') as f:
                for line in f.readlines():
                    if 'THIS_NETWORK_SEGMENT' in line:
                        segment = pickInfo(line)
                    elif 'DHCP_BEGIN_RANGE' in line:
                        net_data['manage_ipstart'] = pickInfo(line)
                    elif 'DHCP_END_RANGE' in line:
                        net_data['manage_ipend'] = pickInfo(line)
                    elif 'THIS_HOST_GATEWAY' in line:
                        net_data['manage_gateway'] = pickInfo(line)
                    elif 'THIS_HOST_DNS' in line:
                        net_data['manage_dns'] = pickInfo(line)
                    elif 'THIS_HOST_NETMASK' in line:
                        mask = str(exchange_mask(pickInfo(line))) 
            net_data['manage_cidr'] = segment + '/' + mask
                
    except Exception as e:
        logger.error(traceback.format_exc())
    return HttpResponse(json.dumps(net_data))

@login_required
def forEnvConfig(request):
    net_data = {}
    try:
        configparser = ConfigParser.ConfigParser()
        configparser.read(OPENSTACK_DEPLOY_CONF)
        
        env_name = getOption(configparser, 'cenvironmentname', 'cenvironmentname')
        networktype = getOption(configparser, 'networkinfo', 'networktype')
        storage_vminstance = getOption(configparser, 'storagetype', 'vminstance')
        storage_vmimage = getOption(configparser, 'storagetype', 'vmimage')
        storage_userdisk = getOption(configparser, 'storagetype', 'userdisk')

        net_data['env_name'] = env_name
        net_data['networktype'] = networktype
        net_data['storage_vminstance'] = storage_vminstance
        net_data['storage_vmimage'] = storage_vmimage
        net_data['storage_userdisk'] = storage_userdisk

    except Exception as e:
        logger.error(traceback.format_exc())
        
    return HttpResponse(json.dumps(net_data))

@login_required
def envConfig(request):
    try:
        form_data = json.loads(request.POST.get('form_data'))

        env_name = form_data.get('setup_name')
        old_pwd = form_data.get('old_pwd')
        new_pwd = form_data.get('new_pwd')
        
#         deploy_mode = request.POST.get('deploy_mode') #部署模式
#         takeover_platform = request.POST.get('takeover_platform') #接管平台
        networktype = form_data.get('network') #网络
    
        storage_vminstance = form_data.get('storage_vminstance') #存储-虚机实例
        storage_vmimage = form_data.get('storage_vmimage') #存储-虚机镜像
        storage_userdisk = form_data.get('storage_userdisk') #存储-用户磁盘
        
        configparser = ConfigParser.ConfigParser()
        configparser.read(OPENSTACK_DEPLOY_CONF)
        #cenvironmentname
        setOption(configparser, 'cenvironmentname', 'cenvironmentname', env_name)
        
        ##networkinfo
        setOption(configparser, 'networkinfo', 'networktype', networktype)
        
        #storagetype
        setOption(configparser, 'storagetype', 'vminstance', storage_vminstance)
        setOption(configparser, 'storagetype', 'vmimage', storage_vmimage)
        setOption(configparser, 'storagetype', 'userdisk', storage_userdisk)
        
        configparser.write(open(OPENSTACK_DEPLOY_CONF,'w'))
        
        # 修改密码
        if old_pwd:
            user_cache = auth.authenticate(username=request.user,password=old_pwd)
            if user_cache is None:
                return HttpResponse('passwd_error')
            else:
                request.user.set_password(new_pwd)
                request.user.save()
    except Exception as e:
        logger.error(traceback.format_exc())
        return HttpResponse('fail')
    return HttpResponse('success')

# 子网掩码格式转换 255.255.255.0 转为 24
def exchange_mask(mask):
    return sum(bin(int(i)).count('1') for i in mask.split('.'))

# 子网掩码格式转换 24 转为 255.255.255.0 
def exchange_prefix(prefix):
    mask = ''
    prefix = int(prefix)
    b_mask = prefix * '1' + (32 - prefix) * '0' # 11111111 11111111 11111111 00000000
    t = ''
    for i in range(32):
        t += b_mask[i]
        if i % 8 == 7:
            if mask:
                mask += '.'
            
            mask += str(int(t, 2))
            t = ''
    return mask

# 获取本机ip
def getLocalIp():
    localip = ''
    (s,o) = commands.getstatusoutput("ifconfig | grep inet[^6] | awk '{print $2}' | grep -v ^127 | head -1")
    if s == 0:
        localip = o
    return localip
        
def getOption(configparser,section,option):
    if configparser.has_option(section,option):
        return configparser.get(section,option)
    return ''

def setOption(configparser,section,option,optionVal):
    if not configparser.has_section(section):
        configparser.add_section(section)
    configparser.set(section,option,optionVal)
    
def clearSection(configparser,section):
    if configparser.has_section(section):
        configparser.remove_section(section)
    configparser.add_section(section)
    
def removeSection(configparser,section):
    if configparser.has_section(section):
        configparser.remove_section(section)

def removeOption(configparser,section,option):
    if configparser.has_option(section,option):
        configparser.remove_option(section,option)
