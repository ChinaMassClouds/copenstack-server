# This if a sample spec file for mcos-openstack

Summary:  mcos-deploy-node-iso
Name:     mcos-deploy-node-iso
Version:  1.1
Release:  1
Vendor:   byq
License:  GPL
Source0:  %{name}-%{version}.tar.gz
Group:    Applications/Text

%description
The mcos-openstack uses to give the node iso.

%prep
%setup -q

%build
%install
#echo `pwd`
install -d %{buildroot}/usr/local/src/
cp Openstack-node-x86_64.tar.gz %{buildroot}/usr/local/src/


%files
/usr/local/src/*




