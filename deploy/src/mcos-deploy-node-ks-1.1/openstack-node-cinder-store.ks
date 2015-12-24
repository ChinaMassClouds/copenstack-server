# kickstart template for Fedora 8 and later.
# (includes %end blocks)
# do not use with earlier distros

#platform=x86, AMD64, or Intel EM64T
# System authorization information
auth  --useshadow  --enablemd5
# System bootloader configuration
bootloader --location=mbr
# Partition clearing information
clearpart --all --initlabel
# Use text mode install
text
# Firewall configuration
firewall --enabled
# Run the Setup Agent on first boot
firstboot --disable
# System keyboard
keyboard us
# System language
lang en_US
# Use network installation
url --url=$tree
# If any cobbler repo definitions were referenced in the kickstart profile, include them here.
$yum_repo_stanza
# Network information
$SNIPPET('network_config')
# Reboot after installation
reboot

# System timezone
timezone Asia/Shanghai --isUtc
user --name=ceph --password=$6$20VYBfwZClN840p.$mjztVmq/D58aGXpSO4H57Cet6rpcM23CDg6X7eSKJriKsymAGNxhlFBb1TRC1tP7FcDhOvklFLTMLjOFxIGzI. --iscrypted --gecos="ceph"

#Root password
rootpw --iscrypted $default_password_crypted
# SELinux configuration
selinux --disabled
# Do not configure the X Window System
skipx
# Install OS instead of upgrade
install
# Clear the Master Boot Record
zerombr
# Allow anaconda to partition the system as needed
part /boot --fstype xfs --size=500 --ondisk=sda
part swap --size=2048 --ondisk=sda
part pv.01 --size=1 --grow --ondisk=sda
volgroup cinder-volumes pv.01 
logvol / --vgname=cinder-volumes --size=10240 --name=lv_root

%pre
$SNIPPET('log_ks_pre')
$SNIPPET('kickstart_start')
$SNIPPET('pre_install_network_config')
# Enable installation monitoring
$SNIPPET('pre_anamon')
%end

%packages
#$SNIPPET('func_install_if_enabled')
@base
@core
chrony
kexec-tools
%end

%post --nochroot
$SNIPPET('log_ks_post_nochroot')
%end

%post
$SNIPPET('log_ks_post')
# Start yum configuration
$yum_config_stanza
# End yum configuration
$SNIPPET('post_install_kernel_options')
$SNIPPET('post_install_network_config')
$SNIPPET('func_register_if_enabled')
$SNIPPET('download_config_files')
$SNIPPET('koan_environment')
$SNIPPET('redhat_register')
$SNIPPET('cobbler_register')
# Enable post-install boot notification
$SNIPPET('post_anamon')
# Start final steps
$SNIPPET('kickstart_done')
# End final steps

sed -i "s/CentOS Linux 7 (Core), with Linux 3.10.0-229.el7.x86_64/Mcos-openstack/g" /etc/grub2.cfg
sed -i "s/CentOS Linux 7 (Core), with Linux 3.10.0-229.el7.x86_64/Mcos-openstack/g" /boot/grub2/grub.cfg
sed -i "s/CentOS Linux 7 (Core), with Linux 0-rescue/Mcos-openstack rescue/g" /etc/grub2.cfg
sed -i "s/CentOS Linux 7 (Core), with Linux 0-rescue/Mcos-openstack rescue/g" /boot/grub2/grub.cfg

echo -e "NAME='Openstack system'\n\
VERSION='1 (Core)'\n\
ID='openstack'\n\
ID_LIKE="rhel fedora"\n\
VERSION_ID='1.1'\n\
PRETTY_NAME='Openstack 1.1'\n\
ANSI_COLOR='0;31'\n\
CPE_NAME='cpe:/o:openstack:openstack:1'\n\
HOME_URL='https://www.centos.org/'\n\
BUG_REPORT_URL='https://bugs.centos.org/'" > /etc/os-release

echo -e "Openstack release" > /etc/system-release
echo -e '    server=master.server.com' >> /etc/puppet/puppet.conf
echo -e '    listen=true' >> /etc/puppet/puppet.conf
sed -i '116a #Allow puppet kick access\npath   /run\nmethod save\nauth any\nallow master.server.com\n' /etc/puppet/auth.conf

echo "ceph ALL = (root)NOPASSWD:ALL" | tee /etc/sudoers.d/ceph
chmod 0440 /etc/sudoers.d/ceph
sed -i "s/Defaults    requiretty/Defaults    !requiretty/g" /etc/sudoers

echo 'password=123456' >> /etc/my.cnf.d/client.cnf
rm /etc/yum.repos.d/CentOS-* -rf

systemctl disable firewalld
systemctl stop firewalld
setenforce 0

systemctl enable nodeInfoUdp
/usr/local/bin/change-dashboard-style
%end
