#-*- coding: utf-8 -*-
import paramiko
#result = os.system("tail -100 /var/log/messages")
#print result
def ssh2(ip,username,passwd,cmd):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(ip,22,username,passwd,timeout=5)
    except Exception as e:
        ssh.close()
        return 'CONNECT_ERROR'
    result = ""
    error_command = ''
    for m in cmd:
        out = ''
        stdin, stdout, stderr = ssh.exec_command(m)
        if stdout:
            out = stdout.readlines()
        if out:
            for o in out:
                result+=o
        elif stderr and stderr.readlines():
            error_command += m + '\n'

    if error_command:
        return 'COMMAND_ERROR:' + error_command
    print '%s\tOK\n'%(ip)
    ssh.close()
    return result


def downloadFile(ip,username,passwd):
    try:
        t=paramiko.Transport((ip,22))
        t.connect(username=username,password=passwd)
        sftp=paramiko.SFTPClient.from_transport(t)
        remotepath='/root/storm-0.9.0.1.zip'
        localpath='/home/data/javawork/pythontest/storm.zip'
        sftp.get(remotepath,localpath)
        print '下载文件成功'
    except Exception, e:
        print '%st 运行失败,失败原因rn%s' % (ip, e)
    finally:
        t.close()
