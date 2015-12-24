from django.conf.urls import patterns, include, url

from django.conf import settings
from mplatform.website.views import Home,About
import os

#from django.contrib import admin
#admin.autodiscover()

urlpatterns = patterns('',
    url(r'^$',Home),
    url(r'^about/$',About),

    url(r'^accounts/',include('UserManage.urls' )),
    url(r'^cplatform/',include('cplatform.urls' )),


    #static
    url(r'^static/(?P<path>.*)$', 'django.views.static.serve', { 'document_root': settings.STATIC_ROOT,}),
)

if settings.DEBUG:
    urlpatterns += patterns('',
url(r'^static/(?P<path>.*)$', 'django.views.static.serve',
{'document_root': os.path.join(settings.BASE_DIR,'static')},name="static"),
    )