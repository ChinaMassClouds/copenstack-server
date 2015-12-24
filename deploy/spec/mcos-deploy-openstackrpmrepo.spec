# This if a sample spec file for mcos-openstack

Summary:  mcos-deploy-openstackrpmrepo
Name:     mcos-deploy-openstackrpmrepo
Version:  1.1
Release:  1
Vendor:   byq
License:  GPL
Source0:  %{name}-%{version}.tar.gz
Group:    Applications/Text

%description
The mcos-openstack uses to give the openstack rpm.

%prep
%setup -q

%build
%install
#echo `pwd`
install -d %{buildroot}/var/www/html
cp openstackrpm.tar.gz %{buildroot}/var/www/html


%files
/var/www/html/*




