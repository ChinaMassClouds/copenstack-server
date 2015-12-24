# Copyright (c) 2014 Cisco Systems, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


from sqlalchemy import Column
from sqlalchemy import MetaData
from sqlalchemy import String
from sqlalchemy import Table


def upgrade(engine):
    """Function adds request_id field."""
    meta = MetaData(bind=engine)

    pci_devices = Table('pci_devices', meta, autoload=True)
    shadow_pci_devices = Table('shadow_pci_devices', meta, autoload=True)
    request_id = Column('request_id', String(36), nullable=True)

    if not hasattr(pci_devices.c, 'request_id'):
        pci_devices.create_column(request_id)

    if not hasattr(shadow_pci_devices.c, 'request_id'):
        shadow_pci_devices.create_column(request_id.copy())


def downgrade(engine):
    """Function drops request_id field."""
    meta = MetaData(bind=engine)

    pci_devices = Table('pci_devices', meta, autoload=True)
    shadow_pci_devices = Table('shadow_pci_devices', meta, autoload=True)

    if hasattr(pci_devices.c, 'request_id'):
        pci_devices.c.request_id.drop()

    if hasattr(shadow_pci_devices.c, 'request_id'):
        shadow_pci_devices.c.request_id.drop()
