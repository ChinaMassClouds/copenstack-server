from horizon import forms
from django.utils.translation import ugettext_lazy as _
import os
import enum
import json
import ConfigParser
import base64
import openstack_dashboard.openstack.common.configparser_tool as cfg_tool
from openstack_dashboard.openstack.common.log import operate_log

class SetMailForm(forms.SelfHandlingForm):
    old_password = forms.CharField(widget=forms.HiddenInput,required=False)
    server_address = forms.CharField(max_length=100,label=_("Mail Server Address"))
    server_port = forms.IntegerField(min_value=0,label=_("Mail Server Port"))
    sender_address = forms.CharField(max_length=100,label=_("Mail Sender Address"))
    sender_username = forms.CharField(max_length=100,label=_("Mail Sender Username"))
    sender_password = forms.CharField(max_length=100,label=_("Mail Sender Password"),
                                      widget=forms.PasswordInput,
                                      required=False,
                                      help_text=_('If the password input is empty, '
                                      'the system will use old password. If you input a new password, '
                                      'that will replace the old one.'))

    def __init__(self, request, *args, **kwargs):
        super(SetMailForm, self).__init__(request, *args, **kwargs)
        
    def clean(self):
        cleaned_data = super(SetMailForm, self).clean()
        if not cleaned_data.get('old_password') and not cleaned_data.get('sender_password'):
            raise forms.ValidationError(_('Please input the mail password.'))
        return cleaned_data
        
    def handle(self, request, data):
        try:
            if not os.path.exists(enum.EMAIL_CFG_FILE):
                os.mknod(enum.EMAIL_CFG_FILE,0777)
            cfgparser = ConfigParser.ConfigParser()
            cfgparser.read(enum.EMAIL_CFG_FILE)
            
            cfg_tool.setOption(cfgparser, 'server', 'ipaddress', data.get('server_address'))
            cfg_tool.setOption(cfgparser, 'server', 'port', data.get('server_port'))
            cfg_tool.setOption(cfgparser, 'sender', 'address', data.get('sender_address'))
            cfg_tool.setOption(cfgparser, 'sender', 'user', data.get('sender_username'))
            if data.get('sender_password'):
                cfg_tool.setOption(cfgparser, 'sender', 'password', base64.b64encode(data.get('sender_password')))
            
            cfgparser.write(open(enum.EMAIL_CFG_FILE,'w'))
            operate_log(request.user.username,
                                request.user.roles,
                                "alter alarm-mail settings success")
            return True
        except Exception as e:
            operate_log(request.user.username,
                                request.user.roles,
                                "alter alarm-mail settings error")
            return False
    
class AddReceiverForm(forms.SelfHandlingForm):
    address = forms.EmailField(label=_('Email Address'))

    def __init__(self, request, *args, **kwargs):
        super(AddReceiverForm, self).__init__(request, *args, **kwargs)

    def clean(self):
        cleaned_data = super(AddReceiverForm, self).clean()
        if os.path.exists(enum.EMAIL_CFG_FILE):
            cfgparser = ConfigParser.ConfigParser()
            cfgparser.read(enum.EMAIL_CFG_FILE)
            if cfg_tool.getOption(cfgparser, 'receiver', 'receiver'):
                receiver = json.loads(cfg_tool.getOption(cfgparser, 'receiver', 'receiver'))
                new_addr = str(cleaned_data.get('address'))
                if new_addr in receiver:
                    raise forms.ValidationError(_('The email address has already exists.'))
        return cleaned_data

    def handle(self, request, data):
        try:
            if not os.path.exists(enum.EMAIL_CFG_FILE):
                os.mknod(enum.EMAIL_CFG_FILE)
            cfgparser = ConfigParser.ConfigParser()
            cfgparser.read(enum.EMAIL_CFG_FILE)
            if cfg_tool.getOption(cfgparser, 'receiver', 'receiver'):
                receiver = json.loads(cfg_tool.getOption(cfgparser, 'receiver', 'receiver'))
            else:
                receiver = []
            new_addr = str(data.get('address'))
            receiver.append(new_addr)
            cfg_tool.setOption(cfgparser, 'receiver', 'receiver', json.dumps(receiver))
            cfgparser.write(open(enum.EMAIL_CFG_FILE,'w'))
            operate_log(request.user.username,
                                request.user.roles,
                                "add mail-receiver \"" + data.get('address') + "\" success")
            return True
        except Exception as e:
            operate_log(request.user.username,
                                request.user.roles,
                                "add mail-receiver \"" + data.get('address') + "\" error")
            return False

