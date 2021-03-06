from django.conf.urls import patterns, include, url

urlpatterns = patterns('cplatform',
    url(r'^findnodes/$', 'views.findnodes', name='findnodesurl'),
    url(r'^listnodes/(?P<targetPage>\d+)/$', 'views.listnodes', name='listnodesurl'),
    url(r'^fornodecfg/(?P<nodename>\w+)/$', 'views.fornodecfg', name='fornodecfgurl'),
    url(r'^create/$', 'views.create', name='createurl'),
    url(r'^deployChange/$', 'views.deployChange', name='deploychangeurl'),
    url(r'^configNode/$', 'views.configNode', name='confignodeurl'),
    url(r'^netConfig/$', 'views.netConfig', name='netconfigurl'),
    url(r'^forNetConfig/$', 'views.forNetConfig', name='fornetconfigurl'),
    url(r'^envConfig/$', 'views.envConfig', name='envconfigurl'),
    url(r'^forEnvConfig/$', 'views.forEnvConfig', name='forenvconfigurl'),
    url(r'^openDhcp/$', 'views.openDhcp', name='opendhcpurl'),
    url(r'^closeDhcp/$', 'views.closeDhcp', name='closedhcpurl'),
    url(r'^installStatus/$', 'views.installStatus', name='installstatusurl'),
    url(r'^logshow/$', 'views.logshow', name='logshowurl'),
    url(r'^deleteEnv/$', 'views.deleteEnv', name='deleteenvurl'),
    url(r'^deleteNode/$', 'views.deleteNode', name='deletenodeurl'),
    url(r'^getDeployStatus/$', 'views.getDeployStatus', name='getdeploystatusurl'), 
    url(r'^uploadBasicIso/$', 'views.uploadBasicIso', name='uploadbasicisourl'),
    url(r'^listBasicIsos/$', 'views.listBasicIsos', name='listbasicisosurl'),
    url(r'^delBasicIso/$', 'views.delBasicIso', name='delbasicisourl'),
    url(r'^uploadUnitRpm/$', 'views.uploadUnitRpm', name='uploadunitrpmurl'),
    url(r'^listUnitRpms/$', 'views.listUnitRpms', name='listunitrpmsurl'),
    url(r'^delUnitRpm/$', 'views.delUnitRpm', name='delunitrpmurl'),
    url(r'^ajaxCreateRepo/$', 'views.ajaxCreateRepo', name='ajaxcreaterepourl'),
    url(r'^basicUpgrade/$', 'views.basicUpgrade', name='basicupgradeurl'),
    url(r'^unitUpgrade/$', 'views.unitUpgrade', name='unitupgradeurl'),
    
    url(r'^downloadHardinfo/$', 'license.downloadHardinfo'),
    url(r'^licenseok/$', 'license.licenseok'),
    url(r'^getHardInfo/$', 'license.getHardInfo'),
    url(r'^getLicenseInfo/$', 'license.getLicenseInfo'),
    url(r'^uploadLicense/$', 'license.uploadLicense'),
    url(r'^getLicenseCpuNo/$', 'license.getLicenseCpuNo'),
)
