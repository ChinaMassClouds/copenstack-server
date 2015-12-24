# This if a sample spec file for mcos-openstack

Summary:  mcos-deploy-cobbler-loaders
Name:     mcos-deploy-cobbler-loaders
Version:  1.1
Release:  1
Vendor:   byq
License:  GPL
Source0:  %{name}-%{version}.tar.gz
Group:    Applications/Text

%description
The mcos-openstack uses to add cobbler loader file.

%prep
%setup -q

%build
%install
#echo `pwd`
install -d %{buildroot}/var/lib/cobbler/loaders
cp COPYING.elilo    %{buildroot}/var/lib/cobbler/loaders
cp COPYING.yaboot   %{buildroot}/var/lib/cobbler/loaders
cp grub-x86_64.efi  %{buildroot}/var/lib/cobbler/loaders
cp menu.c32         %{buildroot}/var/lib/cobbler/loaders
cp README           %{buildroot}/var/lib/cobbler/loaders
cp COPYING.syslinux %{buildroot}/var/lib/cobbler/loaders
cp elilo-ia64.efi   %{buildroot}/var/lib/cobbler/loaders
cp grub-x86.efi     %{buildroot}/var/lib/cobbler/loaders
cp pxelinux.0       %{buildroot}/var/lib/cobbler/loaders
cp yaboot           %{buildroot}/var/lib/cobbler/loaders


%files
/var/lib/cobbler/loaders/*




