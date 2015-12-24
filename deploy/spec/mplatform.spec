Summary:   mplatform
Name:      mplatform
Version:   1.0.0
Release:   Alpha
License:   GPL
Group:     System
Source:    mplatform.tar.gz
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root
Url:       http://www.linuxfly.org
Packager:  Linuxing
Prefix:    %{_prefix}
Prefix:    %{_sysconfdir}
%define    userpath /usr/lib/python2.7/site-packages/

%description
this is management platform.

%prep
%setup -c
%install
install -d $RPM_BUILD_ROOT%{userpath}
cp -a * $RPM_BUILD_ROOT%{userpath}
#cp  $RPM_BUILD_ROOT%{userpath}mplatform/mplatformd /usr/bin/mplatformd
#chmod u+x /usr/bin/mplatformd
%clean
%files
%defattr(-,root,root)
%{userpath}
%post
mkdir -p /var/log/mplatform
mkdir -p /var/lib/mplatform
mkdir -p /etc/mplatform
mkdir -p /data/mplatform
mkdir -p /data/mplatform/uploads/
mkdir -p /data/isos/
mv %{userpath}mplatform/db.sqlite3 /var/lib/mplatform/db.sqlite3
mv %{userpath}mplatform/libcommon.so /lib64/libcommon.so
mv %{userpath}mplatform/libmcoslbaser.so /lib64/libmcoslbaser.so
rm /usr/bin/mplatformd
ln -s %{userpath}mplatform/mplatformd /usr/sbin/mplatformd
chmod u+x /usr/sbin/mplatformd
rm /etc/mplatform/nginx.conf.in
ln -s %{userpath}mplatform/nginx.conf.in /etc/mplatform/nginx.conf.in
ln -s %{userpath}mplatform/shellinaboxd.in /etc/sysconfig/shellinaboxd.in
rm /etc/mplatform/uwsgi_params
ln -s %{userpath}mplatform/uwsgi_params /etc/mplatform/uwsgi_params
cp -f %{userpath}mplatform/mplatform.service /usr/lib/systemd/system/mplatform.service
