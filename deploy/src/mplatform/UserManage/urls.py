from django.conf.urls import patterns, include, url

urlpatterns = patterns('UserManage.views',
    url(r'^login/$', 'user.LoginUser', name='loginurl'),
    url(r'^logout/$', 'user.LogoutUser', name='logouturl'),
    url(r'^user/changepwd/$', 'user.ChangePassword', name='changepasswordurl'),
    url(r'^user/resetpwd/(?P<ID>\d+)/$', 'user.ResetPassword', name='resetpasswordurl'),
)
