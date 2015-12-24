"""
destroy_cached_images.py

This script is used to clean up Glance images that are cached in the SR. By
default, this script will only cleanup unused cached images.

Options:

    --dry_run - Don't actually destroy the VDIs
    --all_cached - Destroy all cached images instead of just unused cached
                   images.
"""
import eventlet
eventlet.monkey_patch()

import os
import sys

from oslo.config import cfg

# If ../nova/__init__.py exists, add ../ to Python search path, so that
# it will override what happens to be installed in /usr/(local/)lib/python...
POSSIBLE_TOPDIR = os.path.normpath(os.path.join(os.path.abspath(sys.argv[0]),
                                   os.pardir,
                                   os.pardir,
                                   os.pardir))
if os.path.exists(os.path.join(POSSIBLE_TOPDIR, 'nova', '__init__.py')):
    sys.path.insert(0, POSSIBLE_TOPDIR)

from nova import config
from nova import utils
from nova.virt.xenapi import driver as xenapi_driver
from nova.virt.xenapi import vm_utils

destroy_opts = [
    cfg.BoolOpt('all_cached',
                default=False,
                help='Destroy all cached images instead of just unused cached'
                     ' images.'),
    cfg.BoolOpt('dry_run',
                default=False,
                help='Don\'t actually delete the VDIs.')
]

CONF = cfg.CONF
CONF.register_cli_opts(destroy_opts)


def main():
    config.parse_args(sys.argv)
    utils.monkey_patch()

    xenapi = xenapi_driver.XenAPIDriver()
    session = xenapi._session

    sr_ref = vm_utils.safe_find_sr(session)
    destroyed = vm_utils.destroy_cached_images(
            session, sr_ref, all_cached=CONF.all_cached,
            dry_run=CONF.dry_run)

    if '--verbose' in sys.argv:
        print '\n'.join(destroyed)

    print "Destroyed %d cached VDIs" % len(destroyed)


if __name__ == "__main__":
    main()
