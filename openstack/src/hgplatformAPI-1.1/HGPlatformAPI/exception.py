#coding:utf-8

class Error(Exception):
    msg = "An unknown exception occurred."
    
    def __init__(self, detail=""):
        super(Error, self).__init__(self)
        self._detail = detail
        
    def __str__(self):
        return repr(self.msg + " " + self._detail)
    
    
class SSHLoginFailed(Error):
    msg = "Ssh failed to connect"
    
class LoginVCenterFailed(Error):
    msg = "Failed to login vcenter, 401"
    
    
class LoginCServerFailed(Error):
    msg = "Failed to login cserver"
    
    
class NoveComputeServiceFailed(Error):
    msg = "Start nova compute service failed"
    
class RequestError(Error):
    msg = "Get request failed"
    
class RequestConnectError(Error):
    msg = "Get connect failed"
    
class CServerLoginFailed(Error):
    msg = "Failed to login cserver"
    
class CServerRequestError(Error):
    msg = "Failed request to cserver"
    
class CServerConnectionError(Error):
    msg = "Failed to connection cserver"
    
class TakeOverVMFailed(Error):
    msg = "Failed to take over vms"
    
class ImageNotFound(Error):
    msg = "Failed to find the image"
    
