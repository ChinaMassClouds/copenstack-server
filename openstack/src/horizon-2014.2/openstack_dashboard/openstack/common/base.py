import socket

def getIpByHostname(hostname):
    try:
        result=socket.getaddrinfo(hostname,None)
        return result[0][4][0]
    except Exception as e:
        return hostname
    
f_getIpByHostname = getIpByHostname