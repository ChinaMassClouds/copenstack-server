#coding:utf-8


class PlatformInstanceInfo(object):
    virt_type = ''
    """
    管理平台的实例信息
    """
    def __init__(self, name, domain_name, hostname, virtualplatformtype, \
                 uuid, session, virtualplatformIP, virtualplatformusername, \
                    virtualplatformpassword, dc_cluster=None):
        self._name = name
        self._domain_name = domain_name
        self._hostname = hostname
        self._virtualplatformtype = virtualplatformtype
        self._uuid = uuid
        self._session = session
        self._dc_cluster = dc_cluster
        self._virtualplatformIP = virtualplatformIP
        self._virtualplatformusername = virtualplatformusername
        self._virtualplatformpassword = virtualplatformpassword
    
    
    @property
    def name(self):
        return self._name
    
    @property
    def domain_name(self):
        return self._domain_name
    
    @property
    def uuid(self):
        return self._uuid
    
    @property
    def dc_cluster(self):
        return self._dc_cluster
    
    @property
    def hostname(self):
        return self._hostname
    
    @property
    def virtualplatformtype(self):
        return self._virtualplatformtype
    
    @property
    def virtualplatformusername(self):
        return self._virtualplatformusername
    
    @property
    def virtualplatformIP(self):
        return self._virtualplatformIP
    
    @property
    def virtualplatformpassword(self):
        return self._virtualplatformpassword
    
    