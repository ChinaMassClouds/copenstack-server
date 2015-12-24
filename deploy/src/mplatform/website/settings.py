#-*- coding: utf-8 -*-
""" 
Django settings for website project.

For more information on this file, see
https://docs.djangoproject.com/en/1.6/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.6/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)

import os
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
FILE_ROOT = '/data/mplatform/uploads/'
ISO_ROOT = '/var/www/html/isos/'
RPM_ROOT = '/var/www/html/packages/'

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.6/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '28ta%!1(r3z17!xq4nh6-5!u_s-v37z!f#0!zt)jy61zwp4)a9'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

TEMPLATE_DEBUG = True

ALLOWED_HOSTS = ['*']

SESSION_COOKIE_AGE = 3 * 60 * 60 # session keep seconds

# Application definition

INSTALLED_APPS = (
    #'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cplatform',
    'UserManage'
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
#     'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
)

ROOT_URLCONF = 'website.urls'

WSGI_APPLICATION = 'website.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.6/ref/settings/#databases
#if 'SERVER_SOFTWARE' in os.environ:
#    from sae.const import (
#        MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASS, MYSQL_DB)
#else:
#    MYSQL_HOST = 'localhost'
#    MYSQL_PORT = '3306'
#    MYSQL_USER = 'root'
#    MYSQL_PASS = ''
#    MYSQL_DB = 'accounts'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join('/var/lib/mplatform/', 'db.sqlite3'),
        #'ENGINE' : 'django.db.backends.mysql',
        #'NAME' : MYSQL_DB,
        #'USER' : MYSQL_USER,
        #'PASSWORD' : MYSQL_PASS,
        #'HOST' : MYSQL_HOST,
        #'PORT' : MYSQL_PORT,
    }
}

# Internationalization
# https://docs.djangoproject.com/en/1.6/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Shanghai'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.6/howto/static-files/

AUTH_USER_MODEL = 'UserManage.User'

STATIC_URL = '/static/'
STATICFILES_DIRS = (
    os.path.join(BASE_DIR,'static'),
)

#set TEMPLATE_DIRS
TEMPLATE_DIRS = [os.path.join(BASE_DIR, 'templates')]

#TEMPLATE zh_CN
FILE_CHARSET='utf-8'
DEFAULT_CHARSET='utf-8'
TEMPLATE_DIRS = (
    os.path.join(BASE_DIR,  'templates'),
)

STATIC_ROOT = '/var/log/mplatform/'


LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(threadName)s:%(thread)d] [%(name)s:%(lineno)d] [%(levelname)s]- %(message)s'
        },
    },
    'filters': {
    },
    'handlers': {
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'include_html': True,
        },
        'default': {
            'level':'DEBUG',
            'class':'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(STATIC_ROOT,'mplatform-db.log'), #或者直接写路径：'c:\logs\all.log',
            'maxBytes': 1024*1024*1024, # 5 MB
            'backupCount': 5,
            'formatter':'standard',
        },
        'main': {
            'level':'DEBUG',
            'class':'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(STATIC_ROOT,'mplatform.log'), #或者直接写路径：'c:\logs\all.log',
            'maxBytes': 1024*1024*1024, # 5 MB
            'backupCount': 5,
            'formatter':'standard',
        },
        'console':{
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'standard'
        },
        'request_handler': {
            'level':'DEBUG',
            'class':'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(STATIC_ROOT,'mflatform-request.log'), #或者直接写路径：'filename':'c:\logs\request.log''
            'maxBytes': 1024*1024*1024, # 5 MB
            'backupCount': 5,
            'formatter':'standard',
        },
        'scprits_handler': {
            'level':'DEBUG',
            'class':'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(STATIC_ROOT,'mflatform-script.log'), #或者直接写路径：'filename':'c:\logs\script.log'
            'maxBytes': 1024*1024*1024, # 5 MB
            'backupCount': 5,
            'formatter':'standard',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['default','console'],
            'level': 'DEBUG',
            'propagate': False
        },
        'UserManage':{
            'handlers': ['main','console'],
            'level': 'DEBUG',
            'propagate': False
        },
        'cplatform':{
            'handlers': ['main','console'],
            'level': 'DEBUG',
            'propagate': False
        },
        
        'django.request': {
            'handlers': ['request_handler'],
            'level': 'DEBUG',
            'propagate': False
        },
        'scripts': { # 脚本专用日志
            'handlers': ['scprits_handler'],
            'level': 'INFO',
            'propagate': False
        },
    }
}