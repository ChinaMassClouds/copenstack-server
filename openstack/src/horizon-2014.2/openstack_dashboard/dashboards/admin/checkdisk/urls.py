from django.conf.urls import patterns
from django.conf.urls import url
from openstack_dashboard.dashboards.admin.checkdisk import views


urlpatterns = patterns('openstack_dashboard.dashboards.admin.checkdisk.views',
    url(r'^$', views.IndexView.as_view(), name='index'),
)
