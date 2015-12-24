#!/bin/bash

CUR_PATH=`pwd`
DSRC_PATH=$CUR_PATH/deploy/src
DSPEC_PATH=$CUR_PATH/deploy/spec
DRPM_CACHE_PATH=$CUR_PATH/drpm_cache
DRPM_SOURCES=$DRPM_CACHE_PATH/SOURCES
DRPM_SPECS=$DRPM_CACHE_PATH/SPECS
DRPM_RPMS=$DRPM_CACHE_PATH/RPMS
ISO_DRPM_PATH=$CUR_PATH/iso/extras/Mcos-extras

#create deploy rpm build cache dir
echo "clean $DRPM_CACHE_PATH"
if [ -d $DRPM_CACHE_PATH ]; then rm -rf $DRPM_CACHE_PATH; fi
mkdir -p {$DRPM_SOURCES,$DRPM_SPECS,$DRPM_RPMS}

#make deploy source to tar file
cd $DSRC_PATH
for subdir in `ls`; do
    if [ -d "$subdir" ]; then
        echo "Compress directory $subdir"
        tar zcvf $subdir.tar.gz $subdir;
        echo ""
    fi
done

#move the tar file to  SOURCES
echo "Move compressed file to $DRPM_SOURCES"
mv ./*.tar.gz $DRPM_SOURCES

#copy the spec file to SPECS
echo "Move deploy spec file to $SPECS"
cp $DSPEC_PATH/*.spec $DRPM_SPECS/

#create the rpm 
cd $DRPM_SPECS
for specs in `ls`; do
    if [ -f "$specs" ]; then
        echo "build $specs to rpm";
        rpmbuild -bb --define="%_topdir $DRPM_CACHE_PATH" $specs;  
    fi
done

cd $DRPM_RPMS/x86_64
rm *debuginfo* -rf

#copy the rpm to iso extras dir"
#cp ${DRPM_RPMS}/x86_64/* ${ISO_DRPM_PATH}/  


 




