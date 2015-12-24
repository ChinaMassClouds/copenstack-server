#coding:utf-8

"""cserver的URL信息"""
CSERVER_DATACENTERS_LIST_URL = '/massclouds-svmanager/api/datacenters'
CSERVER_VM_LIST_URL = '/massclouds-svmanager/api/vms'
CSERVER_VM_DISK_URL = '/massclouds-svmanager/api/vms/%s/disks'
CSERVER_VM_DISK_STATISTICS_URL = '/massclouds-svmanager/api/vms/%s/disks/%s/statistics'
CSERVER_VM_NIC_STATISTICS_URL = '/massclouds-svmanager/api/vms/%s/nics/%s/statistics'
CSERVER_VM_STATICS_URL = '/massclouds-svmanager/api/vms/%s/statistics'
CSERVER_VM_NIC_LIST_URL = '/massclouds-svmanager/api/vms/%s/nics'
CSERVER_HOST_STATICS_URL = '/massclouds-svmanager/api/hosts/%s/statistics'
CSERVER_HOST_NIC_LIST_URL = '/massclouds-svmanager/api/hosts/%s/nics'
CSERVER_HOST_NIC_URL = '/massclouds-svmanager/api/hosts/%s/nics/%s'
CSERVER_HOST_NIC_STATISTICS_URL = '/massclouds-svmanager/api/hosts/%s/nics/%s/statistics'
CSERVER_DC_CLUSTER_LIST_URL = '/massclouds-svmanager/api/datacenters/%s/clusters'
CSERVER_HOST_LIST_URL = '/massclouds-svmanager/api/hosts'
CSERVER_HOST_URL = '/massclouds-svmanager/api/hosts/%s'
CSERVER_DC_STORAGE_URL = '/massclouds-svmanager/api/datacenters/%s/storagedomains'
CSERVER_HOST_STATISTICS_URL = '/massclouds-svmanager/api/hosts/%s/statistics'
CSERVER_TEMPLATE_LIST_URL = '/massclouds-svmanager/api/templates'
CSERVER_TEMPLATE_URL = '/massclouds-svmanager/api/templates/%s/disks'

"""认证失败返回的信息"""
authFailMsg = "Authentication required"

"""openstack的URL信息"""
FLAVOR_DETAILS_URL = "8774/v2/%s/flavors/detail"
FLAVORS_ID_URL = "8774/v2/%s/flavors"
IMAGE_URL = "8774/v2/%s/images"
SERVER_URL = "8774/v2/%s/servers"
TENANT_URL = "5000/v2.0/tenants"
SERVER_METADATA_URL = "8774/v2/%s/servers/%s/metadata/load_vcenter_vm"

"""接管的平台类型"""
VCENTER_TYPE = "vcenter"
CSERVER_TYPE = "cserver"
CDESKTOP = "cdesktop"






