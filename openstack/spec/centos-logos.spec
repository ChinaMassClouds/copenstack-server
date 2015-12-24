%global codename verne
%global dist .el7.centos

Name: centos-logos
Summary: CentOS-related icons and pictures
Version: 70.0.6 
Release: 1%{?dist}
Group: System Environment/Base
URL: http://www.centos.org
# No upstream, done in internal git
Source0: centos-logos-%{version}.tar.xz
License: Copyright © 2014 The CentOS Project.  All rights reserved.

BuildArch: noarch
Obsoletes: gnome-logos
Obsoletes: fedora-logos <= 16.0.2-2
Obsoletes: redhat-logos
Provides: gnome-logos = %{version}-%{release}
Provides: system-logos = %{version}-%{release}
Provides: redhat-logos = %{version}-%{release}
# We carry the GSettings schema override, tell that to gnome-desktop3
Provides: system-backgrounds-gnome
Conflicts: kdebase <= 3.1.5
Conflicts: anaconda-images <= 10
Conflicts: redhat-artwork <= 5.0.5
# For splashtolss.sh
#FIXME: dropped for now since it's not available yet
#BuildRequires: syslinux-perl, netpbm-progs
Requires(post): coreutils
BuildRequires: hardlink
# For _kde4_* macros:
BuildRequires: kde-filesystem

%description
The redhat-logos package (the "Package") contains files created by the
CentOS Project to replace the Red Hat "Shadow Man" logo and  RPM logo.
The Red Hat "Shadow Man" logo, RPM, and the RPM logo are trademarks or
registered trademarks of Red Hat, Inc.

The Package and CentOS logos (the "Marks") can only used as outlined
in the included COPYING file. Please see that file for information on
copying and redistribution of the CentOS Marks.

%prep
%setup -q

%build

%install
# should be ifarch i386
mkdir -p $RPM_BUILD_ROOT/boot/grub
install -p -m 644 -D bootloader/splash.xpm.gz $RPM_BUILD_ROOT/boot/grub/splash.xpm.gz
# end i386 bits

mkdir -p $RPM_BUILD_ROOT%{_datadir}/backgrounds/
for i in backgrounds/*.jpg backgrounds/*.png backgrounds/default.xml; do
  install -p -m 644 $i $RPM_BUILD_ROOT%{_datadir}/backgrounds/
done

mkdir -p $RPM_BUILD_ROOT%{_datadir}/glib-2.0/schemas
install -p -m 644 backgrounds/10_org.gnome.desktop.background.default.gschema.override $RPM_BUILD_ROOT%{_datadir}/glib-2.0/schemas

mkdir -p $RPM_BUILD_ROOT%{_datadir}/gnome-background-properties/
install -p -m 644 backgrounds/desktop-backgrounds-default.xml $RPM_BUILD_ROOT%{_datadir}/gnome-background-properties/

mkdir -p $RPM_BUILD_ROOT%{_datadir}/firstboot/themes/fedora-%{codename}/
for i in firstboot/* ; do
  install -p -m 644 $i $RPM_BUILD_ROOT%{_datadir}/firstboot/themes/fedora-%{codename}/
done

mkdir -p $RPM_BUILD_ROOT%{_datadir}/pixmaps
for i in pixmaps/* ; do
  install -p -m 644 $i $RPM_BUILD_ROOT%{_datadir}/pixmaps
done

mkdir -p $RPM_BUILD_ROOT%{_datadir}/plymouth/themes/charge
for i in plymouth/charge/* ; do
  install -p -m 644 $i $RPM_BUILD_ROOT%{_datadir}/plymouth/themes/charge
done

for size in 16x16 22x22 24x24 32x32 36x36 48x48 96x96 256x256 ; do
  mkdir -p $RPM_BUILD_ROOT%{_datadir}/icons/hicolor/$size/apps
  mkdir -p $RPM_BUILD_ROOT%{_datadir}/icons/Bluecurve/$size/apps
  for i in icons/hicolor/$size/apps/* ; do
    install -p -m 644 $i $RPM_BUILD_ROOT%{_datadir}/icons/hicolor/$size/apps
    cp icons/hicolor/$size/apps/fedora-logo-icon.png $RPM_BUILD_ROOT%{_datadir}/icons/Bluecurve/$size/apps/icon-panel-menu.png
    cp icons/hicolor/$size/apps/fedora-logo-icon.png $RPM_BUILD_ROOT%{_datadir}/icons/Bluecurve/$size/apps/gnome-main-menu.png
    cp icons/hicolor/$size/apps/fedora-logo-icon.png $RPM_BUILD_ROOT%{_datadir}/icons/Bluecurve/$size/apps/kmenu.png
    cp icons/hicolor/$size/apps/fedora-logo-icon.png $RPM_BUILD_ROOT%{_datadir}/icons/Bluecurve/$size/apps/start-here.png
  done
done

mkdir -p $RPM_BUILD_ROOT%{_sysconfdir}
pushd $RPM_BUILD_ROOT%{_sysconfdir}
ln -s %{_datadir}/icons/hicolor/16x16/apps/fedora-logo-icon.png favicon.png
popd

mkdir -p $RPM_BUILD_ROOT%{_datadir}/icons/hicolor/scalable/apps
install -p -m 644 icons/hicolor/scalable/apps/xfce4_xicon1.svg $RPM_BUILD_ROOT%{_datadir}/icons/hicolor/scalable/apps
install -p -m 644 icons/hicolor/scalable/apps/fedora-logo-icon.svg $RPM_BUILD_ROOT%{_datadir}/icons/hicolor/scalable/apps/start-here.svg

(cd anaconda; make DESTDIR=$RPM_BUILD_ROOT install)

for i in 16 22 24 32 36 48 96 256 ; do
  install -p -m 644 -D $RPM_BUILD_ROOT%{_datadir}/icons/hicolor/${i}x${i}/apps/fedora-logo-icon.png $RPM_BUILD_ROOT%{_kde4_iconsdir}/oxygen/${i}x${i}/places/start-here-kde-fedora.png 
done

# ksplash theme
mkdir -p $RPM_BUILD_ROOT%{_kde4_appsdir}/ksplash/Themes/
cp -rp kde-splash/CentOS7/ $RPM_BUILD_ROOT%{_kde4_appsdir}/ksplash/Themes/
pushd $RPM_BUILD_ROOT%{_kde4_appsdir}/ksplash/Themes/CentOS7/2560x1600/
ln -s %{_datadir}/backgrounds/day.jpg background.jpg
ln -s %{_datadir}/pixmaps/system-logo-white.png logo.png
popd

# kdm theme
mkdir -p $RPM_BUILD_ROOT/%{_kde4_appsdir}/kdm/themes/
cp -rp kde-kdm/CentOS7/ $RPM_BUILD_ROOT/%{_kde4_appsdir}/kdm/themes/
pushd $RPM_BUILD_ROOT/%{_kde4_appsdir}/kdm/themes/CentOS7/
ln -s %{_datadir}/pixmaps/system-logo-white.png system-logo-white.png
popd

# kde wallpaper theme
#mkdir -p $RPM_BUILD_ROOT/%{_datadir}/wallpapers/
#cp -rp kde-plasma/CentOS7/ $RPM_BUILD_ROOT/%{_datadir}/wallpapers
#pushd $RPM_BUILD_ROOT/%{_datadir}/wallpapers/CentOS7/contents/images
#ln -s %{_datadir}/backgrounds/day.jpg 2560x1600.jpg
#popd

#pushd $RPM_BUILD_ROOT/%{_datadir}/wallpapers/
#ln -s %{_datadir}/backgrounds .
#popd

# kde desktop theme
mkdir -p $RPM_BUILD_ROOT/%{_kde4_appsdir}/desktoptheme/
cp -rp kde-desktoptheme/* $RPM_BUILD_ROOT/%{_kde4_appsdir}/desktoptheme/

mkdir -p $RPM_BUILD_ROOT%{_datadir}/%{name}
cp -a fedora/*.svg $RPM_BUILD_ROOT%{_datadir}/%{name}

# save some dup'd icons
/usr/sbin/hardlink -v %{buildroot}/

%post
touch --no-create %{_datadir}/icons/hicolor || :
touch --no-create %{_datadir}/icons/Bluecurve || :
touch --no-create %{_kde4_iconsdir}/oxygen ||:

%postun
if [ $1 -eq 0 ] ; then
  touch --no-create %{_datadir}/icons/hicolor || :
  touch --no-create %{_datadir}/icons/Bluecurve || :
  touch --no-create %{_kde4_iconsdir}/oxygen ||:
  gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
  gtk-update-icon-cache %{_datadir}/icons/Bluecurve &>/dev/null || :
  gtk-update-icon-cache %{_kde4_iconsdir}/oxygen &>/dev/null || :
  glib-compile-schemas %{_datadir}/glib-2.0/schemas &> /dev/null || :
fi

%posttrans
gtk-update-icon-cache %{_datadir}/icons/hicolor &>/dev/null || :
gtk-update-icon-cache %{_datadir}/icons/Bluecurve &>/dev/null || :
gtk-update-icon-cache %{_kde4_iconsdir}/oxygen &>/dev/null || :
glib-compile-schemas %{_datadir}/glib-2.0/schemas &> /dev/null || :

%files
%doc COPYING CREDITS
%config(noreplace) %{_sysconfdir}/favicon.png
%{_datadir}/backgrounds/*
%{_datadir}/glib-2.0/schemas/*.override
%{_datadir}/gnome-background-properties/*
%{_datadir}/firstboot/themes/fedora-%{codename}/
%{_datadir}/plymouth/themes/charge/
%{_kde4_iconsdir}/oxygen/
%{_kde4_appsdir}/ksplash/Themes/CentOS7/
%{_kde4_appsdir}/kdm/themes/CentOS7/
#%{_kde4_datadir}/wallpapers/CentOS7/
%{_kde4_appsdir}/desktoptheme/CentOS7/

%{_datadir}/pixmaps/*
%{_datadir}/anaconda/boot/splash.lss
%{_datadir}/anaconda/boot/syslinux-splash.png
%{_datadir}/anaconda/pixmaps/*
%{_datadir}/icons/hicolor/*/apps/*
%{_datadir}/icons/Bluecurve/*/apps/*
%{_datadir}/%{name}/
#%{_datadir}/wallpapers/backgrounds

# we multi-own these directories, so as not to require the packages that
# provide them, thereby dragging in excess dependencies.
%dir %{_datadir}/icons/Bluecurve/
%dir %{_datadir}/icons/Bluecurve/16x16/
%dir %{_datadir}/icons/Bluecurve/16x16/apps/
%dir %{_datadir}/icons/Bluecurve/22x22/
%dir %{_datadir}/icons/Bluecurve/22x22/apps/
%dir %{_datadir}/icons/Bluecurve/24x24/
%dir %{_datadir}/icons/Bluecurve/24x24/apps/
%dir %{_datadir}/icons/Bluecurve/32x32/
%dir %{_datadir}/icons/Bluecurve/32x32/apps/
%dir %{_datadir}/icons/Bluecurve/36x36/
%dir %{_datadir}/icons/Bluecurve/36x36/apps/
%dir %{_datadir}/icons/Bluecurve/48x48/
%dir %{_datadir}/icons/Bluecurve/48x48/apps/
%dir %{_datadir}/icons/Bluecurve/96x96/
%dir %{_datadir}/icons/Bluecurve/96x96/apps/
%dir %{_datadir}/icons/Bluecurve/256x256/
%dir %{_datadir}/icons/Bluecurve/256x256/apps/
%dir %{_datadir}/icons/hicolor/
%dir %{_datadir}/icons/hicolor/16x16/
%dir %{_datadir}/icons/hicolor/16x16/apps/
%dir %{_datadir}/icons/hicolor/22x22/
%dir %{_datadir}/icons/hicolor/22x22/apps/
%dir %{_datadir}/icons/hicolor/24x24/
%dir %{_datadir}/icons/hicolor/24x24/apps/
%dir %{_datadir}/icons/hicolor/32x32/
%dir %{_datadir}/icons/hicolor/32x32/apps/
%dir %{_datadir}/icons/hicolor/36x36/
%dir %{_datadir}/icons/hicolor/36x36/apps/
%dir %{_datadir}/icons/hicolor/48x48/
%dir %{_datadir}/icons/hicolor/48x48/apps/
%dir %{_datadir}/icons/hicolor/96x96/
%dir %{_datadir}/icons/hicolor/96x96/apps/
%dir %{_datadir}/icons/hicolor/256x256/
%dir %{_datadir}/icons/hicolor/256x256/apps/
%dir %{_datadir}/icons/hicolor/scalable/
%dir %{_datadir}/icons/hicolor/scalable/apps/
%dir %{_datadir}/anaconda
%dir %{_datadir}/anaconda/pixmaps
%dir %{_datadir}/anaconda/boot/
%dir %{_datadir}/firstboot/
%dir %{_datadir}/firstboot/themes/
%dir %{_datadir}/plymouth/
%dir %{_datadir}/plymouth/themes/
%dir %{_kde4_sharedir}/kde4/
%dir %{_kde4_appsdir}
%dir %{_kde4_appsdir}/ksplash
%dir %{_kde4_appsdir}/ksplash/Themes/
# should be ifarch i386
/boot/grub/splash.xpm.gz
# end i386 bits

%changelog
* Wed Jul  2 2014 Johnny Hughes <johnny@centos.org> - 70.0.6-1
- New firstboot left bar png

* Mon Jun 23 2014 Jim Perrin <jperrin@centos.org> - 70.0.5-1
- Properly import all backgrounds images
- update poweredby.png
- Add CREDITS for artwork attribution as possible. 
- Update anaconda rnotes images from Tuomas, inspired by Alain

* Tue Jun 10 2014 Jim Perrin <jperrin@centos.org> - 70.0.4-1
- Added updated artwork from Tuomas Kuosmanen
- Added backgrounds from Markus Moeller

* Thu Apr 24 2014 Johnny Hughes <johnny@centos.org> - 70.0.3-99
- updated for the rhel7rc1 release
- renamed centos-logos

* Sat Mar 08 2014 Alain Reguera Delgado <alain.reguera@gmail.com> 69.1.9-2
- Add CentOS brands.
- Add CentOS background images.
- Rename themes from RHEL7 to CentOS7.

* Mon Nov 04 2013 Ray Strode <rstrode@redhat.com> 69.1.9-1
- Fix file conflict
  Resolves: #1025559

* Fri Oct 25 2013 Ray Strode <rstrode@redhat.com> 69.1.8-1
- Update plymouth theme
  Related: #1002219

* Mon Oct 21 2013 Ray Strode <rstrode@redhat.com> 69.1.6-1
- Update syslinux background to black
  Resolves: #1003873
- Prune unused images from anaconda/ after talking to #anaconda

* Wed Jul 31 2013 Ray Strode <rstrode@redhat.com> 69.1.5-1
- Update header image
  Resolves: #988066

* Tue Jul 30 2013 Than Ngo <than@redhat.com> - 69.1.4-1
- cleanup kde theme

* Wed Jul 17 2013 Matthias Clasen <mclasen@redhat.com> 69.1.3-3
- Drop unused old background (#918324)

* Thu Jul 11 2013 Ray Strode <rstrode@redhat.com> 69.1.3-2
- Drop fedora.icns (It brings in an undesirable dependency,
  and we don't support the platform it's designed for
  anyway)

* Wed Apr 24 2013 Than Ngo <than@redhat.com> - 69.1.3-1
- Resolves: #949670, rendering issue in kdm theme
- fix background in kdm theme

* Mon Jan 21 2013 Ray Strode <rstrode@redhat.com> 69.1.2-1
- background reversion fixes.
  Resolves: #884841

* Thu Jan 17 2013 Ray Strode <rstrode@redhat.com> 69.1.1-1
- Revert to earlier header image
  Resolves: #884841

* Wed Nov 14 2012 Ray Strode <rstrode@redhat.com> 69.1.0-1
- Update to latest backgrounds
  Resolves: #860311
- Drop Fedora icon theme
  Resolves: #800475

* Fri Nov  9 2012 Matthias Clasen <mclasen@redhat.com> 69.0.9-3
- Fix a typo in the default background override

* Wed Oct 31 2012 Tomas Bzatek <tbzatek@redhat.com> 69.0.9-2
- Provide the virtual system-backgrounds-gnome for gnome-desktop3

* Tue Oct 30 2012 Ray Strode <rstrode@redhat.com> 69.0.9-1
- Install default background override file here, now that
  desktop-backgrounds-gnome is gone

* Tue Oct 30 2012 Than Ngo <than@redhat.com> - 69.0.8-1
- bz#835922, missing kde wallpaper

* Mon Jun 18 2012 Ray Strode <rstrode@redhat.com> 69.0.7-1
- Update background to RHEL7 branding
  Related: #833137

* Thu May 10 2012 Than Ngo <than@redhat.com> - 69.0.6-1
- add missing kde desktoptheme

* Tue Mar 06 2012 Than Ngo <than@redhat.com> - 69.0.5-1
- bz#798621, add missing kde themes

* Tue Feb 07 2012 Ray Strode <rstrode@redhat.com> 69.0.4-1
- More syslinux splash updates
  Related: #786885

* Fri Feb 03 2012 Ray Strode <rstrode@redhat.com> 69.0.3-1
- Three's a charm?
  Resolves: #786885

* Thu Feb 02 2012 Ray Strode <rstrode@redhat.com> 69.0.2-1
- syslinux splash updates
  Resolves: #786885

* Thu Jan 26 2012 Ray Strode <rstrode@redhat.com> 69.0.1-1
- More updates (problems spotted by stickster)

* Tue Nov 15 2011 Ray Strode <rstrode@redhat.com> - 69.0.0-1
- Resync from fedora-logos-16.0.2-1

* Wed Aug 25 2010 Ray Strode <rstrode@redhat.com> 60.0.14-1
- Update description and COPYING file
  Resolves: #627374

* Fri Jul 30 2010 Ray Strode <rstrode@redhat.com> 60.0.13-1
- Add header image
  Related: #558608

* Fri Jul 16 2010 Ray Strode <rstrode@redhat.com> 60.0.12-1
- Drop glow theme
  Resolves: #615251

* Tue Jun 15 2010 Matthias Clasen <mclasen@redhat.com> 60.0.11-2
- Silence gtk-update-icon-cache in %%post and %%postun
Resolves: #589983

* Fri May 21 2010 Ray Strode <rstrode@redhat.com> 60.0.11-1
- Update anaconda artwork based on feedback
  Resolves: #594825

* Tue May 11 2010 Than Ngo <than@redhat.com> - 60.0.10-1
- update ksplash theme to match the latest splash

* Thu May 06 2010 Ray Strode <rstrode@redhat.com> 60.0.9-1
- Add back grub.splash
  Resolves: 589703
- Add extra frame to plymouth splash
  Related: #558608

* Wed May 05 2010 Ray Strode <rstrode@redhat.com> 60.0.8-1
- Add large logo for compiz easter egg
  Resolves: #582411
- Drop Bluecurve
  Related: #559765
- Install logo icons in System theme
  Related: #566370

* Tue May 04 2010 Ray Strode <rstrode@redhat.com> 60.0.7-1
- Rename firstboot theme to RHEL
  Resolves: #566173
- Add new plymouth artwork
  Related: #558608
- Update backgrounds
- Update anaconda
- Drop gnome-splash
- Drop empty screensaver dir
  Resolves: #576912
- Drop grub splash at request of artists

* Thu Apr 22 2010 Than Ngo <than@redhat.com> - 60.0.6-1
- fix many cosmetic issues in kdm/ksplash theme

* Mon Apr 12 2010 Ray Strode <rstrode@redhat.com> 60.0.5-3
Resolves: #576912
- Readd default.xml

* Fri Apr 09 2010 Ray Strode <rstrode@redhat.com> 60.0.5-2
- Make the upgrade path from alpha a little smoother
  Resolves: #580475

* Wed Apr 07 2010 Ray Strode <rstrode@redhat.com> 60.0.5-1
Resolves: #576912
- Update wallpapers

* Tue Feb 23 2010 Ray Strode <rstrode@redhat.com> 60.0.4-3
Resolves: #559695
- Drop xpm symlinking logic
- hide anaconda image dir behind macro

* Wed Feb 17 2010 Ray Strode <rstrode@redhat.com> 60.0.4-1
Resolves: #565886
- One more update to the KDE artwork
- Revert firstboot theme rename until later since compat link
  is causing problems.

* Wed Feb 17 2010 Ray Strode <rstrode@redhat.com> 60.0.3-1
Resolves: #565886
- Put backgrounds here since they're "trade dress"
- Rename firstboot theme from leonidas to RHEL (with compat link)

* Wed Feb 17 2010 Jaroslav Reznik <jreznik@redhat.com> 60.0.2-1
- KDE theme merged into redhat-logos package
- updated license (year in copyright)

* Fri Feb 05 2010 Ray Strode <rstrode@redhat.com> 60.0.1-3
Resolves: #559695
- spec file cleanups

* Mon Jan 25 2010 Than Ngo <than@redhat.com> - 60.0.1-2
- drop useless leonidas in KDE

* Fri Jan 22 2010 Ray Strode <rstrode@redhat.com> 60.0.1-1
Resolves: #556906
- Add updated artwork for Beta

* Thu Jan 21 2010 Matthias Clasen <mclasen@redhat.com> 60.0.0-2
- Remove a non-UTF-8 char from the spec
 
* Wed Jan 20 2010 Ray Strode <rstrode@redhat.com> 60.0.0-1
Resolves: #556906
- Add bits from glow plymouth theme

* Wed Jan 20 2010 Ray Strode <rstrode@redhat.com> - 11.90.4-1
Resolves: #556906
- Update artwork for Beta

* Tue Dec 08 2009 Dennis Gregorovic <dgregor@redhat.com> - 11.90.3-1.1
- Rebuilt for RHEL 6

* Mon Jun 01 2009 Ray Strode <rstrode@redhat.com> - 11.90.3-1
- remove some of the aliasing from the charge theme

* Thu May 28 2009 Ray Strode <rstrode@redhat.com> - 11.90.0-1
- Update artwork for RHEL 6 alpha

* Thu Jan  4 2007 Jeremy Katz <katzj@redhat.com> - 4.9.16-1
- Fix syslinux splash conversion, Resolves: #209201

* Fri Dec  1 2006 Matthias Clasen <mclasen@redhat.com> - 4.9.15-1
- Readd rhgb/main-logo.png, Resolves: #214868

* Tue Nov 28 2006 David Zeuthen <davidz@redhat.com> - 4.9.14-1
- Don't include LILO splash. Resolves: #216748
- New syslinux-splash from Diana Fong. Resolves: #217493

* Tue Nov 21 2006 David Zeuthen <davidz@redhat.com> - 4.9.13-1
- Make firstboot/splash-small.png completely transparent
- Fix up date for last commit
- Resolves: #216501

* Mon Nov 20 2006 David Zeuthen <davidz@redhat.com> - 4.9.12-1
- New shadowman gdm logo from Diana Fong (#216370)

* Wed Nov 15 2006 David Zeuthen <davidz@redhat.com> - 4.9.10-1
- New shadowman logos from Diana Fong (#215614)

* Fri Nov 10 2006 Than Ngo <than@redhat.com> - 4.9.9-1
- add missing KDE splash (#212130)

* Wed Oct 25 2006 David Zeuthen <davidz@redhat.com> - 4.9.8-1
- Add new shadowman logos (#211837)

* Mon Oct 23 2006 Matthias Clasen <mclasen@redhat.com> - 4.9.7-1 
- Include the xml file in the tarball

* Mon Oct 23 2006 Matthias Clasen <mclasen@redhat.com> - 4.9.6-1
- Add names for the default background (#211556)

* Tue Oct 17 2006 Matthias Clasen <mclasen@redhat.com> - 4.9.5-1
- Update the url pointing to the trademark policy (#187124)

* Thu Oct  5 2006 Matthias Clasen <mclasen@redhat.com> - 4.9.4-1
- Fix some colormap issues in the syslinux-splash (#209201)

* Wed Sep 20 2006 Ray Strode <rstrode@redhat.com> - 4.9.2-1
- ship new artwork from Diana Fong for login screen

* Tue Sep 19 2006 John (J5) Palmieri <johnp@redhat.com> - 1.2.8-1
- Fix packager to dist the xml background file

* Tue Sep 19 2006 John (J5) Palmieri <johnp@redhat.com> - 1.2.7-1
- Add background xml file for the new backgrounds
- Add po directory for translating the background xml

* Tue Sep 19 2006 John (J5) Palmieri <johnp@redhat.com> - 1.2.6-1
- Add new RHEL graphics

* Fri Aug 25 2006 John (J5) Palmieri <johnp@redhat.com> - 1.2.5-1
- Modify the anaconda/splash.png file to say Beta instead of Alpha

* Tue Aug 01 2006 John (J5) Palmieri <johnp@redhat.com> - 1.2.4-1
- Add firstboot-left to the firstboot images

* Fri Jul 28 2006 John (J5) Palmieri <johnp@redhat.com> - 1.2.3-1
- Add attributions to the background graphics metadata
- Add a 4:3 asspect ratio version of the default background graphic

* Thu Jul 27 2006 John (J5) Palmieri <johnp@redhat.com> - 1.2.2-1
- Add default backgrounds

* Wed Jul 12 2006 Matthias Clasen <mclasen@redhat.com> - 1.2.1-1
- Add system lock dialog

* Thu Jun 15 2006 Jeremy Katz <katzj@redhat.com> - 1.2.0-1
- alpha graphics

* Wed Aug  3 2005 David Zeuthen <davidz@redhat.com> - 1.1.26-1
- Add russian localisation for rnotes (#160738)

* Thu Dec  2 2004 Jeremy Katz <katzj@redhat.com> - 1.1.25-1
- add rnotes

* Fri Nov 19 2004 Alexander Larsson <alexl@redhat.com> - 1.1.24-1
- Add rhgb logo (#139788)

* Mon Nov  1 2004 Alexander Larsson <alexl@redhat.com> - 1.1.22-1
- Move rh logo from redhat-artwork here (#137593)

* Fri Oct 29 2004 Alexander Larsson <alexl@redhat.com> - 1.1.21-1
- Fix alignment of gnome splash screen (#137360)

* Fri Oct  1 2004 Alexander Larsson <alexl@redhat.com> - 1.1.20-1
- New gnome splash

* Tue Aug 24 2004 Jeremy Katz <katzj@redhat.com> - 1.1.19-1
- update firstboot splash

* Sat Jun  5 2004 Jeremy Katz <katzj@redhat.com> - 1.1.18-1
- provides: system-logos

* Thu Jun  3 2004 Jeremy Katz <katzj@redhat.com> - 1.1.17-1
- add anaconda bits

* Tue Mar 23 2004 Alexander Larsson <alexl@redhat.com> 1.1.16-1
- fix the logos in the gdm theme

* Fri Jul 18 2003 Havoc Pennington <hp@redhat.com> 1.1.15-1
- build new stuff from garrett

* Wed Feb 26 2003 Havoc Pennington <hp@redhat.com> 1.1.14-1
- build new stuff in cvs

* Mon Feb 24 2003 Jeremy Katz <katzj@redhat.com> 1.1.12-1
- updated again
- actually update the grub splash

* Fri Feb 21 2003 Jeremy Katz <katzj@redhat.com> 1.1.11-1
- updated splash screens from Garrett

* Tue Feb 18 2003 Havoc Pennington <hp@redhat.com> 1.1.10-1
- move in a logo from gdm theme #84543

* Mon Feb  3 2003 Havoc Pennington <hp@redhat.com> 1.1.9-1
- rebuild

* Wed Jan 15 2003 Brent Fox <bfox@redhat.com> 1.1.8-1
- rebuild for completeness

* Mon Dec 16 2002 Havoc Pennington <hp@redhat.com>
- rebuild

* Thu Sep  5 2002 Havoc Pennington <hp@redhat.com>
- add firstboot images to makefile/specfile
- add /usr/share/pixmaps stuff
- add splash screen images
- add COPYING

* Thu Sep  5 2002 Jeremy Katz <katzj@redhat.com>
- add boot loader images

* Thu Sep  5 2002 Havoc Pennington <hp@redhat.com>
- move package to CVS

* Tue Jun 25 2002 Owen Taylor <otaylor@redhat.com>
- Add a shadowman-only derived from redhat-transparent.png

* Thu May 23 2002 Tim Powers <timp@redhat.com>
- automated rebuild

* Wed Jan 09 2002 Tim Powers <timp@redhat.com>
- automated rebuild

* Thu May 31 2001 Owen Taylor <otaylor@redhat.com>
- Fix alpha channel in redhat-transparent.png

* Wed Jul 12 2000 Prospector <bugzilla@redhat.com>
- automatic rebuild

* Mon Jun 19 2000 Owen Taylor <otaylor@redhat.com>
- Add %%defattr

* Mon Jun 19 2000 Owen Taylor <otaylor@redhat.com>
- Add version of logo for embossing on the desktop

* Tue May 16 2000 Preston Brown <pbrown@redhat.com>
- add black and white version of our logo (for screensaver).

* Mon Feb 07 2000 Preston Brown <pbrown@redhat.com>
- rebuild for new description.

* Mon Sep 13 1999 Preston Brown <pbrown@redhat.com>
- added transparent mini and 32x32 round icons

* Sat Apr 10 1999 Michael Fulbright <drmike@redhat.com>
- added rhad logos

* Thu Apr 08 1999 Bill Nottingham <notting@redhat.com>
- added smaller redhat logo for use on web page

* Wed Apr 07 1999 Preston Brown <pbrown@redhat.com>
- added transparent large redhat logo

* Tue Apr 06 1999 Bill Nottingham <notting@redhat.com>
- added mini-* links to make AnotherLevel happy

* Mon Apr 05 1999 Preston Brown <pbrown@redhat.com>
- added copyright

* Tue Mar 30 1999 Michael Fulbright <drmike@redhat.com>
- added 48 pixel rounded logo image for gmc use

* Mon Mar 29 1999 Preston Brown <pbrown@redhat.com>
- package created
