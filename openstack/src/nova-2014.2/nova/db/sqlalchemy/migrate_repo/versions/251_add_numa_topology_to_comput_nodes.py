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
from sqlalchemy import Table
from sqlalchemy import Text


def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    compute_nodes = Table('compute_nodes', meta, autoload=True)
    shadow_compute_nodes = Table('shadow_compute_nodes', meta, autoload=True)

    numa_topology = Column('numa_topology', Text, nullable=True)
    shadow_numa_topology = Column('numa_topology', Text, nullable=True)
    compute_nodes.create_column(numa_topology)
    shadow_compute_nodes.create_column(shadow_numa_topology)


def downgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine

    compute_nodes = Table('compute_nodes', meta, autoload=True)
    shadow_compute_nodes = Table('shadow_compute_nodes', meta, autoload=True)

    compute_nodes.drop_column('numa_topology')
    shadow_compute_nodes.drop_column('numa_topology')
