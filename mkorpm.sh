#!/bin/bash

CUR_PATH=`pwd`
OSRC_PATH=$CUR_PATH/openstack/src
OSPEC_PATH=$CUR_PATH/openstack/spec
OEXT_PATH=$CUR_PATH/openstack/ext
ORPM_CACHE_PATH=$CUR_PATH/orpm_cache
ORPM_SOURCES=$ORPM_CACHE_PATH/SOURCES
ORPM_SPECS=$ORPM_CACHE_PATH/SPECS
ORPM_RPMS=$ORPM_CACHE_PATH/RPMS
ORPM_OPENSTACK_PATH=$CUR_PATH/iso/extras/Openstack

echo "clean $ORPM_CACHE_PATH"
if [ -d $ORPM_CACHE_PATH ]; then rm -rf $ORPM_CACHE_PATH; fi
mkdir -p {$ORPM_SOURCES,$ORPM_SPECS,$ORPM_RPMS}


#make ext source to tar file
cd $OSRC_PATH
for subdir in `ls`; do
    if [ -d "$subdir" ]; then
        echo "Compress directory $subdir"
        if [ "$subdir" == "centos-logos-70.0.6" ]; then
            tar cvf centos-logos-70.0.6.tar centos-logos-70.0.6/ ;
            xz -z centos-logos-70.0.6.tar;
        else
            tar zcvf ${subdir}.tar.gz $subdir;
        fi
	echo ""
    fi
done

#move the tar file to SOURCES
echo "Move compressed file to $ORPM_SOURCES"
mv ./*.tar.gz $ORPM_SOURCES
mv ./*.tar.xz $ORPM_SOURCES

#copy the ext file to SOURCES
cp $OEXT_PATH/* $ORPM_SOURCES/

#create the rpm 
cp $OSPEC_PATH/* $ORPM_SPECS/
cd $ORPM_SPECS
for specs in `ls`; do
    if [ -f "$specs" ]; then
        echo "build $specs to rpm";
        rpmbuild -bb --define="%_topdir $ORPM_CACHE_PATH" $specs;
	[ $? -ne 0 ] && exit 1  
    fi
done


echo "copy the rpm to iso extras dir"
cp ${ORPM_RPMS}/noarch/*.rpm ${ORPM_OPENSTACK_PATH}/  


 




