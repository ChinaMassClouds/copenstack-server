#!/bin/bash
#
# 1. Install Mini CentOS with english.
# 2. Create packages list.
#       cat /root/install.log | grep Installing | sed 's/Installing //g' > ./PackageList.
# 3. Install tools for create iso.
#       yum -y install anaconda repodata createrepo mkisofs rsync 
# 4. Run mcos.sh.
# 5. Root password is rootroot.

# Init EVN.
VERSION=`cat ./iso/version`
#STORAGE=http://192.168.1.40/plibs/storage/cDesktop/
CUR_PATH=`pwd`
DATETIME=`date -d today +"%Y%m%d%H%M"`
DIST=`rpm -E %{dist}`
ISO_NAME=MCOS-Openstack-deploy-V${VERSION}-${DATETIME}.iso
ISO_NAME_VERSION=MCOS-cManager-V${VERSION}.iso
SRC_PATH=/CentOS
CENTOS_ISO=./isos/CentOS-7-x86_64-DVD-1503-01.iso
#CENTOS_ISO=$CUR_PATH/iso/CentOS-7-x86_64-DVD-1503-01.iso
#HTTP_ISO=http://192.168.1.25/cilib/mcos-openstack/iso/CentOS-7-x86_64-DVD-1503-01.iso

TMP_PATH=$CUR_PATH/iso_cache
PKG_LIST=$CUR_PATH/iso/PackageList
PKG_LIST_NUM=`cat $PKG_LIST | wc -l`
PICTURE_RES=${CUR_PATH}/iso/oem/res
ISO_CACHE_DIR=$TMP_PATH
ISO_DRPM_PATH=$CUR_PATH/iso/extras/Mcos-extras
#ISO_ORPM_PATH=$CUR_PATH/iso/extras/Openstack
DRPM_RPMS=$CUR_PATH/drpm_cache/RPMS
ORPM_RPMS=$CUR_PATH/orpm_cache/RPMS
#GIT_URL="git@192.168.1.22:openstack/openstack-manager.git"

if [ -d ${TMP_PATH} ]; then
    rm -rf ${TMP_PATH}
fi
mkdir ${TMP_PATH}

if [ -d $SRC_PATH ]; then umount $SRC_PATH; rm -rf $SRC_PATH; fi
if [ -d $TMP_PATH ]; then rm -rf $TMP_PATH; fi

mkdir -p $SRC_PATH
mkdir -p $TMP_PATH

# Download source code from SVN
:<<!EOF!
cd $CUR_PATH
echo "Update the openstack source code from ${GIT_URL} ..."
git config --global user.name "bi_yqiang"
git config --global user.email "bi_yqiang@massclouds.com"
git pull
[ $? -ne 0 ] && exit 1
!EOF!

# Mount iso to $SRC_PATH.
echo "Mount iso to $SRC_PATH ......"
if [ -f $CENTOS_ISO ]; then
    echo "$CENTOS_ISO exist."
else
#    cd $CUR_PATH/iso
    wget $HTTP_ISO
fi
cd $CUR_PATH
mount -o loop $CENTOS_ISO $SRC_PATH

# Sync cd.
echo "Sync from $SRC_PATH to $TMP_PATH ......"
cd $SRC_PATH
rsync -av --exclude=Packages . $TMP_PATH
mkdir -p $TMP_PATH/Packages

cd $CUR_PATH
./changepic.sh

# Copy rpm to tmp path.
echo "Copy Packages to $TMP_PATH/Packages ......"
i=1
while [ $i -le $PKG_LIST_NUM ] ; do
    line=`head -n $i $PKG_LIST | tail -n -1`
    name=`echo $line | awk '{print $1}'`
    # version=`echo $line | awk '{print $3}' | cut -f 2 -d :`
    UPDATENAME=`find $SRC_PATH/Packages/* -maxdepth 1 -name "$name*" -type f -print`
    # in case the copy failed
    if [ -z "$UPDATENAME" ] ; then
        echo "Not found $SRC_PATH/Packages/$name*."
    else
        echo "cp $SRC_PATH/Packages/$name*."
        cp $SRC_PATH/Packages/$name* $TMP_PATH/Packages/
    fi
    i=`expr $i + 1`
done

# copy extras rpm-packages to $TMP_PATH/Packages
#echo "Copy extras rpm-packages to $TMP_PATH/Packages/ ..."
cpextersrpm() {
for pkg in `find $CUR_PATH/iso/extras/ -name "*.rpm"`; do cp ${pkg} $TMP_PATH/Packages/; done
}

# Copy script file to tmp path.
echo "Copy script to $TMP_PATH/isolinux ......"
rm -rf $TMP_PATH/isolinux/isolinux.cfg
cp $CUR_PATH/iso/script/*.cfg $TMP_PATH/isolinux/
sed -i "s/PRODUCT_NAME/MCOS-Openstack-manager ${VERSION}/" $TMP_PATH/isolinux/isolinux.cfg

#creat openstack rpm
cd ${CUR_PATH}
chmod +x mkorpm.sh
./mkorpm.sh
cp ${ORPM_RPMS}/noarch/*.rpm ./repo/openstackrpmrepo
cp ${ORPM_RPMS}/x86_64/*.rpm ./repo/openstackrpmrepo

#copy the openstack rpm
cd ${CUR_PATH}/repo
echo "make openstackrpm.tar.gz"
tar zcvf openstackrpm.tar.gz ./openstackrpmrepo/
mv -f openstackrpm.tar.gz ${CUR_PATH}/deploy/src/mcos-deploy-openstackrpmrepo-1.1

mkrpm() {
    # generate rpm packages
    cd ${CUR_PATH}
    chmod +x mkdeployrpm.sh
    ./mkdeployrpm.sh
    [ $? -ne 0 ] && exit 1
    rm -f ${ISO_DRPM_PATH}/*
    cp ${DRPM_RPMS}/x86_64/*.rpm ${ISO_DRPM_PATH}/

#    chmod +x mkorpm.sh
#    ./mkorpm.sh
#    rm -rf ${ISO_ORPM_PATH}/*
#    cp ${ORPM_RPMS}/noarch/*.rpm ${ISO_ORPM_PATH}/
#    [ $? -ne 0 ] && exit 1
}

# Change picture.
change_pic() {
    echo "Change picture ......"
    cp -fv $CUR_PATH/res/splash.jpg $TMP_PATH/isolinux/
    mkdir $TMP_PATH/install
    mount -o loop $SRC_PATH/images/install.img $TMP_PATH/install
    if [ -d /tmp/install ]; then rm -rf /tmp/install; fi
    if [ -f /tmp/install.img ]; then rm -rf /tmp/install.img; fi
    rsync -av $TMP_PATH/install /tmp/
    umount $TMP_PATH/install
    cp -fv $CUR_PATH/res/progress_first.png /tmp/install/usr/share/anaconda/pixmaps/
    cp -fv $CUR_PATH/res/progress_first-lowres.png /tmp/install/usr/share/anaconda/pixmaps/
    cp -fv $CUR_PATH/res/splash.png /tmp/install/usr/share/anaconda/pixmaps/
    cp -fv $CUR_PATH/res/syslinux-splash.png /tmp/install/usr/share/anaconda/pixmaps/
    sed -i 's/Minimal/MCOS/g' /tmp/install/usr/lib/anaconda/installclasses/rhel.py
    #cd /tmp/install/usr/share/locale
    #rm -rf ls | egrep -v '(en_us|local.alias|zh_CN)'
    cd /tmp
    mksquashfs install install.img
    cp -fv install.img $TMP_PATH/images/
}

create_yum() {
    cd $TMP_PATH/
    rm -rf $TMP_PATH/repodata/*
    cp $CUR_PATH/iso/script/c7-x86_64-comps.xml $TMP_PATH/repodata/c7-x86_64-comps.xml
    #declare -x discinfo=`head -1 .discinfo`
    createrepo -g $TMP_PATH/repodata/c7-x86_64-comps.xml ./
    #createrepo  -g repodata/c7-x86_64-comps.xml ./
}

# Create iso.
build_iso() {
    echo "Create iso ......"
    cd $TMP_PATH
    rm -f *.iso
    mkisofs -o $ISO_NAME -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -R -J -v -T $TMP_PATH/
    #implantisomd5 $ISO_PATH/$ISO_NAME
    cp $ISO_NAME $ISO_NAME_VERSION
    [ $? -ne 0 ] && exit 1
}

mkiso() {
    mkrpm
    cpextersrpm
    create_yum
#   change_pic
    build_iso
}

mkiso

umount $SRC_PATH; rm -rf $SRC_PATH

