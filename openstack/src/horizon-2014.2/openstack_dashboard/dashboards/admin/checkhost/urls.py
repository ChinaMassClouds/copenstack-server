from django.conf.urls import patterns
from django.conf.urls import url
from openstack_dashboard.dashboards.admin.checkhost import views


urlpatterns = patterns('openstack_dashboard.dashboards.admin.checkhost.views',
    url(r'^$', views.IndexView.as_view(), name='index'),
)
