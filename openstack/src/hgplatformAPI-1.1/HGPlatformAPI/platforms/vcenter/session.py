import netaddr
import suds


SERVICE_INSTANCE = 'ServiceInstance'

class ServiceMessagePlugin(suds.plugin.MessagePlugin):

    def add_attribute_for_value(self, node):
  
        if node.name == 'value':
            node.set('xsi:type', 'xsd:string')

    def marshalled(self, context):
  
        context.envelope.prune()
        context.envelope.walk(self.add_attribute_for_value)

class Service(object):
  
    def __init__(self, wsdl_url=None, soap_url=None):
        self.wsdl_url = wsdl_url
        self.soap_url = soap_url

        self.client = suds.client.Client(self.wsdl_url,
                                         location=self.soap_url,
                                         plugins=[ServiceMessagePlugin()],
                                         cache=suds.cache.NoCache())
        self._service_content = None


    @staticmethod
    def build_base_url(protocol, host, port):
        proto_str = '%s://' % protocol
        host_str = '[%s]' % host if netaddr.valid_ipv6(host) else host
        port_str = '' if port is None else ':%d' % port
        return proto_str + host_str + port_str


class Vim(Service):
   
    def __init__(self, protocol='https', host='localhost', port=None,
                 wsdl_url=None):
 
        base_url = Service.build_base_url(protocol, host, port)
        soap_url = base_url + '/sdk'
        if wsdl_url is None:
            wsdl_url = soap_url + '/vimService.wsdl'
        super(Vim, self).__init__(wsdl_url, soap_url)
    
    @property
    def retrieve_service_content(self):

        moref = suds.sudsobject.Property('ServiceInstance')
        moref._type = 'ServiceInstance'
        return self.client.service.RetrieveServiceContent(moref,SERVICE_INSTANCE)


class VMwareAPISession(object):
    
    def __init__(self,host, server_username, server_password,
                 scheme='https',wsdl_loc=None,port=443):
        
        
        self._host = host
        self._server_username = server_username
        self._server_password = server_password
        self._vim_wsdl_loc = wsdl_loc
        self._session_id = None
        self._vim = None
        self._scheme = scheme
        self._port = port 
        self._create_session()
        
        
    @property
    def vim(self):
        if not self._vim:
            self._vim = Vim(protocol=self._scheme,
                                host=self._host,
                                port=self._port,
                                wsdl_url=self._vim_wsdl_loc)
        return self._vim
    
    def _create_session(self):
        session_manager = self.vim.retrieve_service_content.sessionManager

        session = self.vim.client.service.Login(session_manager,
                                 userName=self._server_username,
                                 password=self._server_password)

        prev_session_id, self._session_id = self._session_id, session.key
      
        self._session_username = session.userName

        if prev_session_id:
            try:
                self.vim.client.service.TerminateSession(session_manager,
                                          sessionId=[prev_session_id])
            except Exception:
                raise Exception
            
    def logout(self):
        if self._session_id:
            
            try:
                self.vim.client.service.Logout(self.vim.client.service.RetrieveServiceContent('ServiceInstance').sessionManager)
                self._session_id = None
            except Exception:
                pass
        else:
                pass

