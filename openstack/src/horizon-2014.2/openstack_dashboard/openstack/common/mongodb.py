import os
import ConfigParser
import base


def getMongodbIp():
    conf = '/etc/ceilometer/ceilometer.conf'
    if os.path.exists(conf):
        cfgParser = ConfigParser.ConfigParser()
        cfgParser.read(conf)
 
        if cfgParser.has_option('database', 'connection'):
            connection_info = cfgParser.get('database', 'connection')
            db_host = connection_info[connection_info.find('@') + 1:]
            db_host = db_host[:db_host.find(':')]
            return base.f_getIpByHostname(db_host)
    return ''

f_getMongodbIp = getMongodbIp