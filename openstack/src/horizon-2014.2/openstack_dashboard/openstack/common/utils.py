

def mysql_read():
    mysql_info = {}
    with open('/etc/openstack.cfg', 'r') as f:
        for i in f.readlines():
            if i.split('=', 1)[0] in ('DASHBOARD_HOST',
                                      'DASHBOARD_PASS',
                                      'DASHBOARD_NAME',
                                      'DASHBOARD_USER',
                                      'DASHBOARD_PORT'):
                data = i.split('=', 1)
                mysql_info[data[0]] = data[1].strip()
    return mysql_info
