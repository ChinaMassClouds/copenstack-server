#coding:utf-8
from flask import Flask, jsonify, request, abort
import json
import sys
from flask import make_response
from manager.hgmanager import HeterogeneousPlatformManager
from utils import com_utils
import time 
from threading import Timer 

app = Flask(__name__)

@app.route('/api/heterogeneous/platform', methods=['GET'])
def get_heterogeneous_platform_dcbase_info():
    """获取异构平台数据中心和集群等基本信息"""
    if not request.json:
        return json.dumps({"errormsg": "need the base data"})
        
    hpManager = HeterogeneousPlatformManager.instance()
    platforms = hpManager.get_platform_dcbase_info(request.json)
    return json.dumps(platforms)


@app.route('/api/heterogeneous/platforms', methods=['GET'])
def get_heterogeneous_platform_list():
    """获取异构平台列表信息"""
    hpManager = HeterogeneousPlatformManager.instance()
    platforms = hpManager.get_heterogeneous_platform_instances()
    return json.dumps(platforms)

@app.route('/api/heterogeneous/platforms/cserver/uuid_maps', methods=['GET'])
def get_cserver_uuid_maps_info():
    """获取openstack与cserver的虚拟机映射信息"""
    hpManager = HeterogeneousPlatformManager.instance()
    cserver_uuid_maps = hpManager.get_cserver_uuid_maps_info()
    return json.dumps(cserver_uuid_maps)

@app.route('/api/heterogeneous/platforms/vcenter/uuid_maps', methods=['GET'])
def get_vcenter_uuid_maps_info():
    """获取openstack与cserver的虚拟机映射信息"""
    hpManager = HeterogeneousPlatformManager.instance()
    vcenter_uuid_maps = hpManager.get_vcenter_uuid_maps_info()
    return json.dumps(vcenter_uuid_maps)

@app.route('/api/heterogeneous/platforms/datacenters', methods=['GET'])
def get_heterogeneous_datacenters_list():
    """获取所有异构平台下的数据中心信息"""
    hpManager = HeterogeneousPlatformManager.instance()
    datacenters = hpManager.get_allhp_datacenter_info()
    return json.dumps(datacenters)


@app.route('/api/heterogeneous/platforms/clusters', methods=['GET'])
def get_heterogeneous_cluster_list():
    """获取所有异构平台下的集群信息"""
    hpManager = HeterogeneousPlatformManager.instance()
    clusters = hpManager.get_allhp_cluster_info()
    return json.dumps(clusters)


@app.route('/api/heterogeneous/platforms/hosts', methods=['GET'])
def get_heterogeneous_hosts_list():
    """获取所有异构平台下的主机信息"""
    hpManager = HeterogeneousPlatformManager.instance()
    hosts = hpManager.get_allhp_host_info()
    return json.dumps(hosts)

@app.route('/api/heterogeneous/platforms/cserver/templates', methods=['GET'])
def get_cserver_platform_template_list():
    """获取指定cserver平台下的模板信息"""
    if not request.json:
        return json.dumps({"errormsg": "Get cserver templates need the platform name"})
    
    hpManager = HeterogeneousPlatformManager.instance()
    hosts = hpManager.get_cserver_template_list(request.json)
    return json.dumps(hosts)


@app.route('/api/heterogeneous/platforms/cserver/clusters', methods=['GET'])
def get_cserver_platform_clusters_list():
    """获取指定cserver平台下的集群信息"""
    if not request.json:
        return json.dumps({"errormsg": "Get cserver clusters need the platform name"})
    
    hpManager = HeterogeneousPlatformManager.instance()
    hosts = hpManager.get_cserver_cluster_info_list(request.json)
    return json.dumps(hosts)

@app.route('/api/heterogeneous/platforms/cserver/vms', methods=['GET'])
def get_cserver_platform_vms_list():
    """获取指定cserver平台下的虚拟机信息"""
    if not request.json:
        return json.dumps({"errormsg": "Get cserver vms need the platform name"})
    
    hpManager = HeterogeneousPlatformManager.instance()
    vms = hpManager.get_cserver_vm_list(request.json)
    return json.dumps(vms)

@app.route('/api/heterogeneous/platforms/vcenter/vms', methods=['GET'])
def get_vcenter_platform_vms_list():
    """获取指定vcenter平台下的虚拟机信息"""
    if not request.json:
        return json.dumps({"errormsg": "Get vcenter vms need the platform name"})
    
    hpManager = HeterogeneousPlatformManager.instance()
    vms = hpManager.get_vcenter_vm_list(request.json)
    return json.dumps(vms)

@app.route('/api/heterogeneous/platforms/<string:uuid>', methods=['GET'])
def get_specify_platform_instance_info(uuid):
    """获取指定平台下的信息"""
    platform_uuid = uuid
    hpManager = HeterogeneousPlatformManager.instance()
    result = hpManager.get_specify_platform_instance_info(platform_uuid)
    return json.dumps(result)

@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'errormsg': 'Not found'}), 404)

@app.errorhandler(400)
def bad_request(error):
    return make_response(jsonify({'errormsg': 'Bad request'}), 400)

@app.route('/api/heterogeneous/platforms', methods=['POST'])
def add_heterogeneous_platform():
    """添加异构平台"""
    print "json......", request.json
    
    if not request.json:
        return json.dumps({"errormsg": "need the base data"})
        
    
    hpManager = HeterogeneousPlatformManager.instance()
    result = hpManager.add_heterogeneous_platform_instance(request.json)
    return json.dumps(result)


@app.route('/api/heterogeneous/platforms/<string:uuid>', methods=['DELETE'])
def delete_heterogeneous_platform(uuid):
    """删除异构平台"""
    if not request.json:
        return json.dumps({"errormsg": "need the base data"})

    hpManager = HeterogeneousPlatformManager.instance()
    result = hpManager.remove_heterogeneous_platform_instance(request.json)
    return json.dumps(result)


@app.route('/api/heterogeneous/platforms/sync', methods=['POST'])
def sync_heterogeneous_platform():
    """同步异构平台"""
    if not request.json:
        return json.dumps({"errormsg": "need the base data"})
        
    hpManager = HeterogeneousPlatformManager.instance()
    result = hpManager.sync_heterogeneous_platform_instance(request.json)
    return json.dumps(result)


if __name__ == '__main__':
    host_ip = com_utils.get_controller_node_address()
     
    if len(sys.argv) <= 1:
        app.run(host = host_ip, debug=True, port=5001)
    elif sys.argv[1] == "stop":
        print "stop the web service"
    elif sys.argv[1] == "start":
        print "start the web service"
        app.run(host = host_ip, debug=True, port=5001)
