# This if a sample spec file for mcos-openstack

Summary:  mcos-deploy-setup
Name:     mcos-deploy-setup
Version:  1.1
Release:  1
Vendor:   byq
License:  GPL
Source0:  %{name}-%{version}.tar.gz
Group:    Applications/Text

%description
The mcos-openstack uses to config openstack environment.

%prep
%setup -q

%build
%install
#echo `pwd`
install -d %{buildroot}/usr/local/bin
cp setdeploynode %{buildroot}/usr/local/bin
cp setdhcp %{buildroot}/usr/local/bin
cp ipsetup %{buildroot}/usr/local/bin

install -d %{buildroot}/usr/share/deployboard
cp deployboard.py %{buildroot}/usr/share/deployboard
cp tsTserv.py %{buildroot}/usr/share/deployboard
cp changeNodesHost.py %{buildroot}/usr/share/deployboard
cp openStkDeployment.py %{buildroot}/usr/share/deployboard
cp deployAddNodes.py %{buildroot}/usr/share/deployboard

install -d %{buildroot}/usr/share/python-lib-src
cp pexpect-2.3.tar.gz %{buildroot}/usr/share/python-lib-src

install -d %{buildroot}/etc/
cp dhcp_config %{buildroot}/etc/
cp deploy_node_config %{buildroot}/etc/

%files
/usr/*
/etc/*
/usr/share/*

