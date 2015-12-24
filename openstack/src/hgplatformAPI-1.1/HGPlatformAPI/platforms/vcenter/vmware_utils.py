
def build_selection_spec(client_factory, name):
  
    sel_spec = client_factory.create('ns0:SelectionSpec')
    sel_spec.name = name
    return sel_spec


def build_traversal_spec(client_factory, name, type_, path, skip, select_set):
 
    traversal_spec = client_factory.create('ns0:TraversalSpec')
    traversal_spec.name = name
    traversal_spec.type = type_
    traversal_spec.path = path
    traversal_spec.skip = skip
    traversal_spec.selectSet = select_set
    return traversal_spec


def build_recursive_traversal_spec(client_factory):

    visit_folders_select_spec = build_selection_spec(client_factory,
                                                     'visitFolders')
    # Next hop from Datacenter
    dc_to_hf = build_traversal_spec(client_factory,
                                    'dc_to_hf',
                                    'Datacenter',
                                    'hostFolder',
                                    False,
                                    [visit_folders_select_spec])
    dc_to_vmf = build_traversal_spec(client_factory,
                                     'dc_to_vmf',
                                     'Datacenter',
                                     'vmFolder',
                                     False,
                                     [visit_folders_select_spec])
    dc_to_netf = build_traversal_spec(client_factory,
                                      'dc_to_netf',
                                      'Datacenter',
                                      'networkFolder',
                                      False,
                                      [visit_folders_select_spec])

    # Next hop from HostSystem
    h_to_vm = build_traversal_spec(client_factory,
                                   'h_to_vm',
                                   'HostSystem',
                                   'vm',
                                   False,
                                   [visit_folders_select_spec])

    # Next hop from ComputeResource
    cr_to_h = build_traversal_spec(client_factory,
                                   'cr_to_h',
                                   'ComputeResource',
                                   'host',
                                   False,
                                   [])
    cr_to_ds = build_traversal_spec(client_factory,
                                    'cr_to_ds',
                                    'ComputeResource',
                                    'datastore',
                                    False,
                                    [])

    rp_to_rp_select_spec = build_selection_spec(client_factory, 'rp_to_rp')
    rp_to_vm_select_spec = build_selection_spec(client_factory, 'rp_to_vm')

    cr_to_rp = build_traversal_spec(client_factory,
                                    'cr_to_rp',
                                    'ComputeResource',
                                    'resourcePool',
                                    False,
                                    [rp_to_rp_select_spec,
                                     rp_to_vm_select_spec])

    # Next hop from ClusterComputeResource
    ccr_to_h = build_traversal_spec(client_factory,
                                    'ccr_to_h',
                                    'ClusterComputeResource',
                                    'host',
                                    False,
                                    [])
    ccr_to_ds = build_traversal_spec(client_factory,
                                     'ccr_to_ds',
                                     'ClusterComputeResource',
                                     'datastore',
                                     False,
                                     [])
    ccr_to_rp = build_traversal_spec(client_factory,
                                     'ccr_to_rp',
                                     'ClusterComputeResource',
                                     'resourcePool',
                                     False,
                                     [rp_to_rp_select_spec,
                                      rp_to_vm_select_spec])
    # Next hop from ResourcePool
    rp_to_rp = build_traversal_spec(client_factory,
                                    'rp_to_rp',
                                    'ResourcePool',
                                    'resourcePool',
                                    False,
                                    [rp_to_rp_select_spec,
                                     rp_to_vm_select_spec])
    rp_to_vm = build_traversal_spec(client_factory,
                                    'rp_to_vm',
                                    'ResourcePool',
                                    'vm',
                                    False,
                                    [rp_to_rp_select_spec,
                                     rp_to_vm_select_spec])

    # Get the assorted traversal spec which takes care of the objects to
    # be searched for from the rootFolder
    traversal_spec = build_traversal_spec(client_factory,
                                          'visitFolders',
                                          'Folder',
                                          'childEntity',
                                          False,
                                          [visit_folders_select_spec,
                                           h_to_vm,
                                           dc_to_hf,
                                           dc_to_vmf,
                                           dc_to_netf,
                                           cr_to_ds,
                                           cr_to_h,
                                           cr_to_rp,
                                           ccr_to_h,
                                           ccr_to_ds,
                                           ccr_to_rp,
                                           rp_to_rp,
                                           rp_to_vm])
    return traversal_spec


def build_property_spec(client_factory, type_='VirtualMachine',
                        properties_to_collect=None, all_properties=False):

    if not properties_to_collect:
        properties_to_collect = ['name']

    property_spec = client_factory.create('ns0:PropertySpec')
    property_spec.all = all_properties
    property_spec.pathSet = properties_to_collect
    property_spec.type = type_
    return property_spec

def build_object_spec(client_factory, root_folder, traversal_specs):
  
    object_spec = client_factory.create('ns0:ObjectSpec')
    object_spec.obj = root_folder
    object_spec.skip = False
    object_spec.selectSet = traversal_specs
    return object_spec

def build_property_filter_spec(client_factory, property_specs, object_specs):

    property_filter_spec = client_factory.create('ns0:PropertyFilterSpec')
    property_filter_spec.propSet = property_specs
    property_filter_spec.objectSet = object_specs
    return property_filter_spec

def get_objects(vim, type_):

    properties_to_collect = None

    if not properties_to_collect:
        properties_to_collect = ['name']

    client_factory = vim.client.factory
    recur_trav_spec = build_recursive_traversal_spec(client_factory)

    object_spec = build_object_spec(client_factory,
                                    vim.retrieve_service_content.rootFolder,
                                    [recur_trav_spec])

    property_spec = build_property_spec(client_factory,
                                        type_=type_,
                                        properties_to_collect=properties_to_collect,
                                        all_properties=False)

    property_filter_spec = build_property_filter_spec(client_factory,
                                                      [property_spec],
                                                      [object_spec])

    options = client_factory.create('ns0:RetrieveOptions')
    options.maxObjects = 100
    return vim.client.service.RetrievePropertiesEx(vim.retrieve_service_content.propertyCollector,
                                    specSet=[property_filter_spec],
                                    options=options)
    

def get_objects_by_path(vim,type_,path):
    properties_to_collect = None

    if not properties_to_collect:
        properties_to_collect = ['name']

    client_factory = vim.client.factory
    recur_trav_spec = build_recursive_traversal_spec(client_factory)

    object_spec = build_object_spec(client_factory,path,[recur_trav_spec])

    property_spec = build_property_spec(client_factory,type_=type_,
                                        properties_to_collect=properties_to_collect,
                                        all_properties=False)

    property_filter_spec = build_property_filter_spec(client_factory,[property_spec],
                                                      [object_spec])

    options = client_factory.create('ns0:RetrieveOptions')
    options.maxObjects = 100
    return vim.client.service.RetrievePropertiesEx(vim.retrieve_service_content.propertyCollector, specSet=[property_filter_spec],
                                                   options=options)
    
    
    
def get_object_properties(vim, collector, mobj, type_, properties):

    client_factory = vim.client.factory
    if mobj is None:
        return None
    usecoll = collector
    if usecoll is None:
        usecoll = vim.retrieve_service_content.propertyCollector
        
    property_filter_spec = client_factory.create('ns0:PropertyFilterSpec')
    
    property_spec = client_factory.create('ns0:PropertySpec')
    property_spec.all = (properties is None or len(properties) == 0)
    property_spec.pathSet = properties
    property_spec.type = type_
    
    object_spec = client_factory.create('ns0:ObjectSpec')
    object_spec.obj = mobj
    object_spec.skip = False
    
    property_filter_spec.propSet = [property_spec]
    property_filter_spec.objectSet = [object_spec]
    
    options = client_factory.create('ns0:RetrieveOptions')
    options.maxObjects = 100
    
    return vim.client.service.RetrievePropertiesEx(usecoll, specSet=[property_filter_spec],options=options)








#----------------------------------------------------------------------------------------------------------------------------------------------------------#
