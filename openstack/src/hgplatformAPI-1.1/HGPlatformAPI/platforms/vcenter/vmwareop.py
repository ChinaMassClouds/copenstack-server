#coding:utf-8

from vmware_utils  import get_object_properties
from vmware_utils  import get_objects


def get_vc_version(session):
    '''
    获取vCenter 的 版本
     
    :param session :与vCenter 服务建立的会话连接对象
    :return : 返回vCenter的版本信息
    '''
    return session.vim.retrieve_service_content.about.version


def get_dict_prop(properties):
    '''
    将属性对象转化成字典
    
    :param properties : 属性对象列表
    :return ：以字典模式返回属性集合
    '''
    prop_dict = {}
    for p in properties:
        prop_dict[str(p.name)]=str(p.val)
      
    return prop_dict

def get_datastore_info(session,datastore_moref):
    '''
    获取存储对象信息
    
    :param session :与vCenter 服务建立的会话连接对象
    :param datastore_moref : datastore 的管理应用对象
    :return : 以元组形式返回datastore的总容量和空闲空间
    '''
   
    datastore_Summary = get_object_properties(session.vim, None, datastore_moref, 'Datastore',['summary',])
    datastore_summary = datastore_Summary.objects[0].propSet[0].val
    
    return (datastore_summary.capacity,datastore_summary.freeSpace)

def get_object_datastore(session,moref,type_):
    '''
    获取对象的存储信息
    
    :param session :与vCenter 服务建立的会话连接对象
    :param moref :所要查询的对象
    :param type_ :查询对象的类型
    
    :return 元组(totalCapacity,freeCapacity)
    '''
    totalCapacity =0
    freeCapacity =0  
    result = get_object_properties(session.vim, None,moref, type_, ['datastore'])
    
    ob_moref = result.objects[0]
    if not ob_moref.propSet[0].val:
        return (totalCapacity,freeCapacity)
    
    list_datastore = ob_moref.propSet[0].val.ManagedObjectReference
    for datastore in list_datastore:
        capacity = get_datastore_info(session,datastore)
        totalCapacity = totalCapacity +capacity[0]
        freeCapacity = freeCapacity +capacity[1]
    return (totalCapacity,freeCapacity)
   

def get_moref_group(session,moref,type_,properties):
    '''
    获取管理引用对象的group 属性对象
    
    :param session :与vCenter 服务建立的会话连接对象
    :param moref : 管理对象引用
    :param type_ :管理对象引用的类型
    :param properties:属性集合
    :return 返回属性group 的对象
    '''
    group_list = []
    result = get_object_properties(session.vim, None, moref, type_, properties).objects

    for ob in result :
        group_list.append(ob.propSet[0].val)
    return group_list

def get_tuple_dc(object_context):
    '''
    获取所有的数据中心的名字和数据中心管理引用对象
    
    :param object_context :Datacenter 对象
    :return 返回数据中心的名字和管理引用对象
    '''
    dc_ob = object_context.obj
    if hasattr(object_context, 'propSet'):
        dc_name = object_context.propSet[0].val
        return (dc_name,dc_ob)
        
    return None

def list_datacenter(session):  
    '''
    获取数据中心列表
    
    :param session :与vCenter 服务建立的会话连接对象
    :return 数据中心信息列表(列表的元素是一个元组(dc_name,dc_moref))
    '''
    list_result =[]
    list_dc = get_objects(session.vim,'Datacenter')
    for index1 in range(len(list_dc)):
        for index2  in range(len(list_dc[index1])):
            dc_info = get_tuple_dc(list_dc[index1][index2])
            if dc_info:
                list_result.append(dc_info)
    return list_result



def is_cluster_morf_by_name(moref,name):
    '''
    判断 name 的值是否与moref.propSet[0].val的值相等
    如果一致 返回 True 否则 返回 False
    
    :param moref :集群管理引用对象
    :param name : 所要获得的集群名称
    '''
    if hasattr(moref, 'propSet') and moref.propSet[0].val == name:
        return True
    return False
    
def get_cluster_ref(session,cluster_name):
    '''
    根据指定的集群列表
    
    :param session :与vCenter 服务建立的会话连接对象
    :param cluster_name :集群的名字
    :return 返回 cluster_moref的列表
    '''
    list_result =[]
    result = get_objects(session.vim,'ClusterComputeResource')
  
    for index1 in range(len(result)):
        for index2  in range(len(result[index1])):
            if is_cluster_morf_by_name(result[index1][index2],cluster_name):
                list_result.append(result[index1][index2].obj)        
    return list_result

def get_cluster_list_name(session):
    '''
    获取集群的名称列表
    
    :param session :与vCenter 服务建立的会话连接对象
    :return 返回 cluster名称的列表
    '''
    cluster_name_list = []
    cluster_list = get_objects(session.vim,'ClusterComputeResource')
    for objs in cluster_list:
        for o in objs:
            if isinstance(o, str):
                continue
            for item in o:
                name = item.propSet[0].val
                cluster_name_list.append(name)
                
    return cluster_name_list
             
             
def get_cluster_cpu(session,cluster_moref):
    '''
    获取集群的cpu资源 
    
    :param session :与vCenter 服务建立的会话连接对象
    :param cluster_moref :集群的管理对象引用
    :return 返回cpu资源 单位hz
    '''
    ob = get_object_properties(session.vim, None, cluster_moref, 'ClusterComputeResource',['summary.totalCpu',]).objects[0]
    if hasattr(ob, 'propSet'):
        prop_val = ob.propSet[0].val
    return prop_val

def get_cluster_memSize(session,cluster_moref):
    '''
    获取集群中内存大小
    
    :param session :与vCenter 服务建立的会话连接对象
    :param cluster_moref : 集群的管理对象引用
    :return prop_val 内存大小 
    '''
    prop_val = 0
    ob = get_object_properties(session.vim, None, cluster_moref, 'ClusterComputerResource',['summary.totalMemory',]).objects[0]
    if hasattr(ob, 'propSet'):
        prop_val = ob.propSet[0].val
    return prop_val

def get_dc_cluster(session,dc_moref):
    '''
    获取指定数据中心下的集群列表
    
    :param session :与vCenter 服务建立的会话连接对象
    :param dc_moref :数据中心管理对象引用
    
    :return 元组(cluster_name,cluster_moref)的列表
    '''
    list_cluster = []
    group_moref_datacenter = get_moref_group(session,dc_moref,'Datacenter',['hostFolder'])
    if not group_moref_datacenter:
        return list_cluster
    
    datacenter_folder = group_moref_datacenter[0].value
    
    for name in get_cluster_list_name(session):
        list_cluster_ref = get_cluster_ref(session,name)
        for cluster_moref in list_cluster_ref:
            group_moref_cluster =  get_moref_group(session,cluster_moref,'ClusterComputeResource',['parent'])
            
            if not group_moref_cluster:
                continue
            
            cluster_folder = group_moref_cluster[0].value
            
            if datacenter_folder == cluster_folder:
                list_cluster.append((str(name), cluster_moref))
                
    return list_cluster

    

def get_host_info(session,moref,properties):
    '''
    获取主机基本信息
    
    :param session :与vCenter 服务建立的会话连接对象
    :param moref : 主机管理对象引用
    :param properties :s=主机管理对象的属性集合
    :return list_prop 的属性列表
    '''
    list_prop = []
    result = get_object_properties(session.vim, None, moref, 'HostSystem', properties)
    list_ob = result.objects
    for ob in list_ob:
        if hasattr(ob, 'propSet'):
            prop = ob.propSet
            list_prop.append(get_dict_prop(prop))
    return list_prop

def get_host_status(session,host_moref):
    '''
    获取主机的状态
    
    :param session :与vCenter 服务建立的会话连接对象
    :param host_moref : 主机管理对象引用
    :return 主机的状态
    '''
    ob = get_object_properties(session.vim, None, host_moref, 'HostSystem',['summary.overallStatus',]).objects[0]
    if hasattr(ob, 'propSet'):
        prop = ob.propSet
        return get_dict_prop(prop).get('summary.overallStatus', 'unknown')
    return 'unknown'

def get_host_cpu_info(session,host_moref):
    '''
    获取主机的cpu信息
    
    :param session :与vCenter 服务建立的会话连接对象
    :param host_moref : 主机管理对象引用
    :return 主机的cpu信息
    '''
    ob = get_object_properties(session.vim, None, host_moref, 'HostSystem',['hardware.cpuInfo',]).objects[0]
    if hasattr(ob, 'propSet'):
        prop = ob.propSet[0].val
#         print "prop..........:", prop
        return [prop.numCpuCores * prop.numCpuCores, prop.hz]
    return []

def get_host_memSize(session,host_moref):
    '''
    获取主机的内存
    
    :param session :与vCenter 服务建立的会话连接对象
    :param host_moref : 主机管理对象引用
    :return 主机的内存
    '''
    memSize = 0
    ob = get_object_properties(session.vim, None, host_moref, 'HostSystem',['hardware.memorySize',]).objects[0]
    if hasattr(ob, 'propSet'):
        memSize = ob.propSet[0].val
    
    return memSize


def get_host_ip(session,host_moref):
    list_ip = []
    result = get_object_properties(session.vim, None, host_moref, 'HostSystem', ['name',])
    list_ob = result.objects
    for ob in list_ob:
        if hasattr(ob, 'propSet') and ob.propSet[0].name == 'name':
            list_ip.append(str(ob.propSet[0].val))   
    return list_ip

def get_cluster_host(session,cluster_moref):
    '''
    获取指定集群下的主机
    
    :param session:与vCenter 服务建立的会话连接对象
    :param cluster_moref :管理对象引用
    :return Host 列表
    '''
    list_host = []
    Host = []
    cluster_prop = get_object_properties(session.vim, None, cluster_moref, 'ClusterComputeResource', ['host',])
    ob =  cluster_prop.objects[0]
    if hasattr(ob,'propSet'):
        list_host = ob.propSet[0].val. ManagedObjectReference

    for host in list_host:
        list_ip = get_host_ip(session,host)
        Host.append((list_ip,host.value, host))
    return Host


def get_vm_info(session,moref,properties):
    '''
    :param session :与vCenter 服务建立的会话连接对象
    :param moref :主机的管理对象引用
    :param properties:属性集合
    :return 属性值的字典集合
    '''
    list_prop = []
    result = get_object_properties(session.vim, None, moref, 'VirtualMachine', properties)
    list_ob = result.objects
    for ob in list_ob:
        if hasattr(ob, 'propSet'):
            prop = ob.propSet
            list_prop.append(get_dict_prop(prop))
    return list_prop


def get_vm_name_uuid(session, moref):
    list_info = {}
    result = get_object_properties(session.vim, None, moref, 'VirtualMachine', ['name','config.instanceUuid'])
    list_ob = result.objects
    for ob in list_ob:
        if hasattr(ob, 'propSet'):
            for prop in ob.propSet:
                if prop.name == 'name':
                    list_info['name'] = prop.val
                else:
                    list_info['id'] = prop.val
                 

    return  list_info

def get_vm_num_cpu(session,vm_morf):
    result = get_object_properties(session.vim, None, vm_morf, 'VirtualMachine', ['config.hardware.numCPU']) 
    ob = result.objects[0]   
    if hasattr(ob, 'propSet') :
        return ob.propSet[0].val
    return -1

# def get_vm_ip(session, vm_morf):
#     result = get_object_properties(session.vim, None, vm_morf, 'VirtualMachine', ['network']) 
#     res = result.objects[0].propSet[0].val.ManagedObjectReference[0]
#     print res
#     Res = get_object_properties(session.vim, None, res, 'Network', ['summary.ipPoolName'])
#     return Res

    
    
def get_vm_memSize(session,vm_morf):
    result = get_object_properties(session.vim, None, vm_morf, 'VirtualMachine', ['config.hardware.memoryMB']) 
    ob = result.objects[0]   
    if hasattr(ob, 'propSet') :
        return ob.propSet[0].val
    return -1

def get_vm_diskSize(session,vm_morf):
    list_devcie = get_object_properties(session.vim, None, vm_morf, 'VirtualMachine', ['config.hardware.device']).objects[0].propSet[0].val.VirtualDevice
    for dev in list_devcie :
        if  hasattr(dev, 'capacityInKB'):
            return  dev.capacityInKB
    return -1

def get_vm_power_status(session,vm_morf):
    result = get_object_properties(session.vim, None, vm_morf, 'VirtualMachine', ['summary.runtime.powerState'])
    ob = result.objects[0]   
    if hasattr(ob, 'propSet'):   
        return str(ob.propSet[0].val)
    return "unknown"

def get_vm_runtime_cpuUsage(session,vm_moref):
    datastrore_moref = get_object_properties(session.vim, None, vm_moref, 'VirtualMachine', ['resourcePool',]).objects[0].propSet[0].val
    cpu_usage = get_object_properties(session.vim, None, datastrore_moref, 'ResourcePool', ['runtime.cpu.overallUsage',])
    return cpu_usage
    
def get_vm_runtime_memUsage(session,vm_moref):
    datastrore_moref = get_object_properties(session.vim, None, vm_moref, 'VirtualMachine', ['resourcePool',]).objects[0].propSet[0].val
    memory_usage=get_object_properties(session.vim, None, datastrore_moref, 'ResourcePool', ['runtime.memory.overallUsage',])
    return memory_usage

def get_vm_info_list(session,host_moref):
    list_vms = []
    list_vms_info = []
    host_prop = get_object_properties(session.vim, None, host_moref, 'HostSystem', ['vm',])
    ob =  host_prop.objects[0]
    if hasattr(ob,'propSet'):
        if not ob.propSet[0].val:
            return list_vms_info
        list_vms = ob.propSet[0].val.ManagedObjectReference
        
    for vm in list_vms:
        vm_info = {}
        vm_info.update(get_vm_name_uuid(session, vm))
        vm_info["cpu"] = get_vm_num_cpu(session, vm)
        vm_info["ram"] = get_vm_memSize(session, vm)
        vm_info["power_state"] = get_vm_power_status(session, vm)
        vm_info["disk"] = get_vm_diskSize(session, vm)/1024.0/1024.0
        vm_info["host"] = host_moref.value
        list_vms_info.append(vm_info)
    return list_vms_info



