# This if a sample spec file for mcos-openstack

Summary:  hgplatformAPI
Name:     hgplatformAPI
Version:  1.1
Release:  1
Vendor:   byq
License:  GPL
Source0:  %{name}-%{version}.tar.gz
Group:    Applications/Text

%description
The mcos-openstack uses to take over others platforms vms.

%prep
%setup -q

%build
%install
#echo `pwd`
install -d %{buildroot}/usr/share/
cp -r HGPlatformAPI    %{buildroot}/usr/share/

install -d %{buildroot}/lib/systemd/system/
cp HGPlatform.service %{buildroot}/lib/systemd/system

install -d %{buildroot}/usr/local/bin/
cp HGPlatform        %{buildroot}/usr/local/bin
cp deletevm.sh       %{buildroot}/usr/local/bin

%files
/usr/share/*
/lib/systemd/system/*
/usr/local/bin/*


