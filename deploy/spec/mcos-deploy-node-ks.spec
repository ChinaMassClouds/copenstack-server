# This if a sample spec file for mcos-openstack

Summary:  mcos-deploy-node-ks
Name:     mcos-deploy-node-ks
Version:  1.1
Release:  1
Vendor:   byq
License:  GPL
Source0:  %{name}-%{version}.tar.gz
Group:    Applications/Text

%description
The mcos-deploy-node-ks is used to offer the ks file for base iso

%prep
%setup -q

%build
%install
#echo `pwd`
install -d %{buildroot}/var/lib/cobbler/kickstarts/
cp openstack-node-common.ks %{buildroot}/var/lib/cobbler/kickstarts/
cp openstack-node-cinder-store.ks %{buildroot}/var/lib/cobbler/kickstarts/

%files
/var/lib/cobbler/kickstarts/*



