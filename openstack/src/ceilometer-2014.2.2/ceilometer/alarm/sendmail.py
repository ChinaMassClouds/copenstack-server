# -*- coding: utf-8 -*-

import sys
import json
from optparse import OptionParser

import ConfigParser
from smtplib import SMTP
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import base64
import logging

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)

LOG.addHandler(handler)

ALARM_CONFIG_FILE = "/etc/massclouds/mail_alarm.cfg"

def send(message):
    ''' Return True if sucessful '''
    # Create message container - the correct MIME type is multipart/alternative.
    
    email_info = get_email_base_info()
    print email_info
    if not email_info["From"] or not email_info["To"]:
        LOG.error("option from/to email address must be specified")
        return False
    if not email_info["user"] or not email_info["passwd"]:
        LOG.error("option user/passwd must be specified")
        return False

    server = email_info["server"]
    sender = email_info["From"]
    receiver = email_info["To"]
    subject = email_info["Subject"]
    user = email_info["user"]
    passwd = email_info["passwd"]
    receiver_str = ",".join(receiver)

    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['To'] = receiver_str
    msg['Subject'] = subject
    body = MIMEText(message, 'plain')
    # Attach parts into message container.
    # According to RFC 2046, the last part of a multipart message, in this case
    # the HTML message, is best and preferred.
    msg.attach(body)
    #LOG.info("%s" % msg.as_string())
    LOG.info("msg: %s", msg.as_string())
    try:
        smtp = SMTP(server)
        smtp.ehlo()
        smtp.starttls()
        smtp.login(user, passwd)
        smtp.sendmail(msg['From'], receiver, msg.as_string())
        LOG.info("Successfully sent the mail")
        return True
    except :
        LOG.error("Failed to send mail")
        LOG.error("\t%s", sys.exc_info()[0])
        return False


def get_email_base_info():
    conf = ConfigParser.ConfigParser() 
    conf.read(ALARM_CONFIG_FILE)
    server_address = conf.get("server", "ipaddress", "")
    sender = conf.get("sender", "address", "")
    receiver = json.loads(conf.get("receiver", "receiver"))
    subject = "Openstack alarm"
    user = sender
    passwd = base64.b64decode(conf.get("sender", "password", ""))
    return {
            "server": server_address,
            "From": sender,
            "To": receiver,
            "Subject": subject,
            "user": user,
            "passwd": passwd,
            
            }




