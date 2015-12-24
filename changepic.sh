#!/bin/bash


CUR_PATH=`pwd`
TMP_PATH=$CUR_PATH/iso_cache
RES_PATH=$CUR_PATH/iso/res
SCRIPT_PATH=$CUR_PATH/iso/script
MOUNT_SQASHFS_IMG_PATH=$TMP_PATH/sqashfs-img
MOUNT_ROOTFS_IMG_PATH=$TMP_PATH/rootfs-img
SQASHFS_IMG_PATH=$TMP_PATH/sqashfs

if [ -d $MOUNT_SQASHFS_IMG_PATH ]; then umount $MOUNT_SQASHFS_IMG_PATH; rm -rf $MOUNT_SQASHFS_IMG_PATH;fi
if [ -d $MOUNT_ROOTFS_IMG_PATH ]; then umount $MOUNT_ROOTFS_IMG_PATH; rm -rf $MOUNT_ROOTFS_IMG_PATH;fi
if [ -d $SQASHFS_IMG_PATH ]; then rm -rf $SQASHFS_IMG_PATH; fi

mkdir -p $MOUNT_SQASHFS_IMG_PATH
mkdir -p $MOUNT_ROOTFS_IMG_PATH
mkdir -p $SQASHFS_IMG_PATH

echo "mount $TMP_PATH/LiveOS/squashfs.img on $MOUNT_SQASHFS_IMG_PATH"
mount -o loop $TMP_PATH/LiveOS/squashfs.img $MOUNT_SQASHFS_IMG_PATH

echo "cp $MOUNT_SQASHFS_IMG_PATH/LiveOS to $SQASHFS_IMG_PATH ..........."
cp -rf $MOUNT_SQASHFS_IMG_PATH/LiveOS $SQASHFS_IMG_PATH
#exit 1
echo "umount $MOUNT_SQASHFS_IMG_PATH"
umount $MOUNT_SQASHFS_IMG_PATH

#exit 1
echo "mount $SQASHFS_IMG_PATH/LiveOS/rootfs.img on $MOUNT_ROOTFS_IMG_PATH"
mount -o loop $SQASHFS_IMG_PATH/LiveOS/rootfs.img $MOUNT_ROOTFS_IMG_PATH
echo "replace the pixmaps....."
cp -rf $RES_PATH/anaconda/theme/* $MOUNT_ROOTFS_IMG_PATH/usr/share/anaconda/pixmaps/
cp -rf $RES_PATH/anaconda/rnotes/en/* $MOUNT_ROOTFS_IMG_PATH/usr/share/anaconda/pixmaps/rnotes/en/
cp -rf $RES_PATH/pixmaps/* $MOUNT_ROOTFS_IMG_PATH/usr/share/pixmaps/
cp -rf $SCRIPT_PATH/.buildstamp $MOUNT_ROOTFS_IMG_PATH/
echo "umount $MOUNT_ROOTFS_IMG_PATH"
umount $MOUNT_ROOTFS_IMG_PATH


cd $CUR_PATH/iso
mksquashfs sqashfs squashfs.img
echo "mv squashfs.img to $TMP_PATH/LiveOS/"
mv squashfs.img $TMP_PATH/LiveOS/

cd $CUR_PATH
rm -rf $MOUNT_SQASHFS_IMG_PATH
rm -rf $MOUNT_ROOTFS_IMG_PATH
rm -rf $SQASHFS_IMG_PATH







