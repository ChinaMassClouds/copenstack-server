#!/bin/bash

source /etc/openstack.cfg

if [ "$CONTROLLER_NODE_IP" == "$MARIADB_NODE_IP" ]; then
    mysql -uroot << EOF
use nova;
DELETE FROM security_group_instance_association where instance_uuid="$1";
DELETE FROM instance_info_caches WHERE instance_uuid='$1';
DELETE FROM nova.block_device_mapping where instance_uuid="$1";
DELETE FROM instance_extra WHERE instance_uuid='$1';
DELETE FROM instance_extra WHERE instance_uuid='$1';
DELETE FROM instance_actions_events WHERE action_id IN (SELECT id FROM instance_actions WHERE instance_uuid='$1');
delete from instance_actions where instance_uuid="$1";
delete from instance_metadata where instance_uuid="$1";
delete from instance_system_metadata where instance_uuid="$1";
delete from instance_faults where instance_uuid="$1";
delete from instances where uuid="$1";
use neutron;
DELETE FROM ipallocations where port_id=(select id from ports where device_id="$1");
DELETE FROM ports where device_id="$1";
EOF
else
    mysql -h $MARIADB_NODE_IP -u root -p$MARIADB_USER_PASS<<EOF
use nova;
DELETE FROM security_group_instance_association where instance_uuid="$1";
DELETE FROM instance_info_caches WHERE instance_uuid='$1';
DELETE FROM nova.block_device_mapping where instance_uuid="$1";
DELETE FROM instance_extra WHERE instance_uuid='$1';
DELETE FROM instance_extra WHERE instance_uuid='$1';
DELETE FROM instance_actions_events WHERE action_id IN (SELECT id FROM instance_actions WHERE instance_uuid='$1');
delete from instance_actions where instance_uuid="$1";
delete from instance_metadata where instance_uuid="$1";
delete from instance_system_metadata where instance_uuid="$1";
delete from instance_faults where instance_uuid="$1";
delete from instances where uuid="$1";
use neutron;
DELETE FROM ipallocations where port_id=(select id from ports where device_id="$1");
DELETE FROM ports where device_id="$1";
EOF
fi


