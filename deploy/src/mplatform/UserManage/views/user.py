#!/usr/bin/env python
#-*- coding: utf-8 -*-
#update:2014-09-12 by liufeily@163.com

from django.core.urlresolvers import reverse
from django.http import HttpResponse,HttpResponseRedirect
from django.shortcuts import render_to_response,RequestContext
from django.contrib.auth.decorators import login_required
from mplatform.website.common.CommonPaginator import SelfPaginator
from django.contrib import auth
from django.contrib.auth import get_user_model
 
def LoginUser(request):
    '''用户登录view'''
#     if request.user.is_authenticated():
#         return HttpResponseRedirect('/')

    if request.method == "POST":
        login_user = request.POST.get('login_user')
        login_passwd = request.POST.get('login_passwd')
        user_cache = auth.authenticate(username=login_user,password=login_passwd)
        if user_cache is None:
            return render_to_response('login.html',{"errormsg":"密码错误"},RequestContext(request))
        elif not user_cache.is_active:
            return render_to_response('login.html',{"errormsg":"此账号已被禁用"},RequestContext(request))
            
        auth.login(request, user_cache)
        return HttpResponseRedirect('/')


    kwvars = {
        'request':request
    }

    return render_to_response('login.html',kwvars,RequestContext(request))

@login_required
def LogoutUser(request):
    auth.logout(request)
    return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def ChangePassword(request):
    if request.method=='POST':
        form = ChangePasswordForm(user=request.user,data=request.POST)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('logouturl'))
    else:
        form = ChangePasswordForm(user=request.user)

    kwvars = {
        'form':form,
        'request':request,
    }

    return render_to_response('UserManage/password.change.html',kwvars,RequestContext(request))


@login_required
def ResetPassword(request,ID):
    user = get_user_model().objects.get(id = ID)

    newpassword = get_user_model().objects.make_random_password(length=10,allowed_chars='abcdefghjklmnpqrstuvwxyABCDEFGHJKLMNPQRSTUVWXY3456789')
    print '====>ResetPassword:%s-->%s' %(user.username,newpassword)
    user.set_password(newpassword)
    user.save()

    kwvars = {
        'object':user,
        'newpassword':newpassword,
        'request':request,
    }

    return render_to_response('UserManage/password.reset.html',kwvars,RequestContext(request))