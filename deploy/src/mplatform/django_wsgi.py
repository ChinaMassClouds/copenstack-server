#-*- coding: utf-8 -*-
import os
import django.core.handlers.wsgi
os.environ['DJANGO_SETTINGS_MODULE'] = 'website.settings'    #这里的my_django.settings 表示 "项目名.settings"
#application = django.core.handlers.wsgi.WSGIHandler()
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
