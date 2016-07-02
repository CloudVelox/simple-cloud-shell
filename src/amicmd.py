#
# Copyright 2014-2016 CloudVelox Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
#
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""This module contains the implementation of the 'ami' command
"""

import getopt

from boto.ec2.blockdevicemapping import BlockDeviceMapping, BlockDeviceType

import common

from common import CommandError
from common import confirm_aggr
from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector

_VALID_ARCH = ['i386', 'x86_64']


def _preprocess(ami_list, disp):
    """Preprocess the ami_list according to the disp (which is
    of type DisplayOptions)
    """
    if disp.display == DisplayOptions.LONG and disp.display_name:
        return sorted(ami_list, key=lambda ami: ami.name)
    else:
        return ami_list


class AMICommand(common.BaseCommand):
    """Implementation of the 'ami' command
    """

    def __ami_display(self, ami, disp, pg, region):
        """Display AMI info
        """
        if disp.display == DisplayOptions.LONG:
            if disp.display_name:
                last_field = ami.name
            else:
                last_field = ''
            pg.prt("%-14s %-10s %-14s %-5s %s",
                    ami.id, ami.architecture, ami.kernel_id,
                    ami.virtualization_type,
                    last_field)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", ami.id)
            pg.prt("%15s : %-12s", "State", ami.state)
            pg.prt("%15s : %s", "Location", ami.location)
            pg.prt("%15s : %s", "Name", ami.name)
            pg.prt("%15s : %s", "Public", ami.is_public)
            pg.prt("%15s : %s", "Owner", ami.owner_id)
            pg.prt("%15s : %s", "Description", ami.description)
            pg.prt("%15s : %s %s %s", "Hardware",
                                        ami.architecture,
                                        ami.virtualization_type,
                                        ami.hypervisor,
                                        )
            pg.prt("%15s : %s %s %s", "Software",
                                        ami.platform,
                                        ami.kernel_id,
                                        ami.ramdisk_id)
            pg.prt("%15s : %-12s %s", "Root",
                                        ami.root_device_name,
                                        ami.root_device_type)
            bdev_list = ami.block_device_mapping.keys()
            bdev_list.sort()
            for bdev in bdev_list:
                bdev_info = ami.block_device_mapping[bdev]
                pg.prt("%15s : %-12s %12s dot=%s",
                        "Device", bdev,
                        bdev_info.snapshot_id if bdev_info.snapshot_id else
                                bdev_info.ephemeral_name,
                        bdev_info.delete_on_termination)
            if disp.display_tags:
                common.display_tags(ami.tags, pg)
        else:
            pg.prt("%s", ami.id)
            if disp.display_tags:
                common.display_tags(ami.tags)

    def __ami_list_cmd(self, region, selector, disp, owner_list):
        """Implements the list function of the ami command
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        if selector.resource_id_list:
            owner_list = None
        elif not owner_list:
            owner_list = ['self']
        ami_list = ec2_conn.get_all_images(
                                        image_ids=selector.resource_id_list,
                                        owners=owner_list,
                                        filters=selector.get_filter_dict())
        self.cache_insert(region, [ami.id for ami in ami_list])
        with CommandOutput() as pg:
            disp_ami_list = _preprocess(ami_list, disp)
            for ami in disp_ami_list:
                self.__ami_display(ami, disp, pg, region)

    def __ami_delete(self, region, selector):
        """Implements the deletion function of the ami command
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        if selector.is_explicit():
            ami_id_list = selector.resource_id_list
        else:
            ami_list = ec2_conn.get_all_images(
                                owners=['self'],
                                filters=selector.get_filter_dict())
            ami_id_list = [ami.id for ami in ami_list]
        if not confirm_aggr("Will delete:", ami_id_list):
            return
        for ami_id in ami_id_list:
            ec2_conn.deregister_image(ami_id)
            self.cache_remove(region, [ami_id])

    def __update_bdm(self, bdm, bd_spec):
        """Update the BlockDeviceMapping bdm with the block device
        spec bd_spec.
        """
        try:
            dev_name, dev_value = bd_spec.split('=', 1)
        except Exception:
            raise CommandError(
                "Block device spec missing '=' : %s" % (bd_spec,))
        dot = None
        bdt = BlockDeviceType()
        if ':' in dev_value:
            blockdev_origin, dot = dev_value.split(':', 1)
        else:
            blockdev_origin = dev_value
        if blockdev_origin is None:
            raise CommandError("No source specified for %s" % (dev_name,))
        if blockdev_origin.startswith('ephemeral'):
            bdt.ephemeral_name = blockdev_origin
        elif blockdev_origin.startswith('snap-'):
            bdt.snapshot_id = blockdev_origin
        else:
            raise CommandError("Bad source specified for %s: %s" % (dev_name,
                                                        blockdev_origin))
        if dot is not None:
            if dot == 'delete':
                bdt.delete_on_termination = True
            elif dot == 'nodelete':
                bdt.delete_on_termination = False
            else:
                raise CommandError(
                        "Bad delete-on-termination specified for %s: %s" %
                                        (dev_name, dot))
        else:
            bdt.delete_on_termination = False
        dev_path = '/dev/' + dev_name
        bdm[dev_path] = bdt

    def __ami_create_from_ami(self, region, description,
                                        source_ami_id, source_region):
        """Create an AMI by copying an AMI from anothe region
        """
        ec2_conn = self.get_ec2_conn(region)
        copy_image = ec2_conn.copy_image(source_region,
                                            source_ami_id, description)
        return copy_image.image_id

    def __ami_create_from_instance(self, region, description, ami_name,
                                                                instance_id):
        """Create an AMI from an existing instance
        """
        ec2_conn = self.get_ec2_conn(region)
        ami_id = ec2_conn.create_image(instance_id,
                                        name=ami_name,
                                        description=description,
                                        no_reboot=True)
        return ami_id

    def __ami_create_detailed(self, region, description, ami_name,
                                arch, root_devname, virt_type,
                                aki_id, ari_id, bdm):
        """Create an AMI from all the information necessary to create
        an AMI.
        """
        if arch is None:
            raise CommandError("No architecture specified; use one of: %s" %
                        (",".join(_VALID_ARCH),))
        if root_devname is None:
            raise CommandError("No root device name specified")
        if virt_type is not None:
            valid_virt_types = ['paravirtual', 'hvm']
            if virt_type == 'pv':
                virt_type = 'paravirtual'
            if virt_type not in valid_virt_types:
                raise CommandError(
                        "Invalid virtualization type: %s; use one of %s" %
                        (virt_type, ",".join(valid_virt_types)))
        if virt_type == 'hvm':
            aki_id = None
            ari_id = None
        else:
            if aki_id is None:
                raise CommandError("No AKI specified")
        if root_devname.startswith('/dev/'):
            root_devpath = root_devname
        else:
            root_devpath = '/dev/' + root_devname
        ec2_conn = self.get_ec2_conn(region)
        ami_id = ec2_conn.register_image(
                                name=ami_name,
                                description=description,
                                architecture=arch,
                                kernel_id=aki_id,
                                ramdisk_id=ari_id,
                                root_device_name=root_devpath,
                                block_device_map=bdm,
                                virtualization_type=virt_type)
        return ami_id

    def __ami_create(self, region, description, virt_type, arg_list):
        """Create (register in EC2-parlance) a new AMI.
        Example:
            ami -C sda1=snap-12345678:delete aki-12345678
        """
        instance_id = None
        aki_id = None
        ari_id = None
        arch = None
        ami_name = None
        source_ami_id = None
        source_region = None
        bdm = BlockDeviceMapping()
        root_devname = None
        saved_args = []
        for arg in arg_list:
            if arg.startswith('sd'):
                self.__update_bdm(bdm, arg)
            elif arg in _VALID_ARCH:
                arch = arg
            elif arg.startswith('name='):
                ami_name = arg.split('=', 1)[1]
            elif arg.startswith('root='):
                root_devname = arg.split('=', 1)[1]
            elif arg.startswith('aki-'):
                aki_id = arg
            elif arg.startswith('ari-'):
                ari_id = arg
            elif arg.startswith('i-'):
                instance_id = arg
            elif arg.startswith('ami-'):
                source_ami_id = arg
            else:
                # It could be the source region, if we are copying an AMI
                saved_args.append(arg)
        if source_ami_id is None:
            # We are creating an AMI from scratch
            if ami_name is None:
                print "You must specify a name for the new AMI"
                return
            if instance_id is not None:
                ami_id = self.__ami_create_from_instance(region, description,
                                                        ami_name, instance_id)
            else:
                ami_id = self.__ami_create_detailed(region, description,
                                ami_name,
                                arch, root_devname, virt_type,
                                aki_id, ari_id, bdm)
        else:
            # We are copying an AMI
            if not saved_args:
                print "Missing source region"
                return
            elif len(saved_args) > 1:
                print "Expecting 2 arguments: source ami-id, source region"
                return
            source_region = saved_args[0]
            ami_id = self.__ami_create_from_ami(region, description,
                                                source_ami_id, source_region)
        self.cache_insert(region, [ami_id])
        print ami_id

    def __ami_cmd(self, argv):
        """Implements the ami command
        """
        cmd_delete = False
        cmd_create = False
        description = None
        virtualization_type = None
        selector = ResourceSelector()
        disp = DisplayOptions()
        region = None
        owner_list = []
        opt_list, args = getopt.getopt(argv, "aCd:Df:lnq:r:tU:v:x")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    selector.select_all = True
                elif opt[0] == '-C':
                    cmd_create = True
                elif opt[0] == '-d':
                    description = opt[1]
                elif opt[0] == '-D':
                    cmd_delete = True
                elif opt[0] == '-f':
                    selector.add_filter_spec(opt[1])
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-n':
                    disp.display_name = True
                elif opt[0] == '-q':
                    selector.add_tag_filter_spec(opt[1])
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-t':
                    disp.display_tags = True
                elif opt[0] == '-U':
                    owner_list.append(opt[1])
                elif opt[0] == '-v':
                    virtualization_type = opt[1]
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if cmd_delete:
            selector.resource_id_list = args
            self.__ami_delete(region, selector)
        elif cmd_create:
            self.__ami_create(region, description, virtualization_type, args)
        else:
            selector.resource_id_list = args
            self.__ami_list_cmd(region, selector, disp, owner_list)

    def do_ami(self, ln):
        """
        ami [std-options] [list-options] [-C] [-D] [ami-id] ...

Options:
    -C          : create a new AMI
    -D          : delete an existing AMI
    -d desc     : AMI description (when creating a new AMI)
    -U owner    : list AMIs owned by 'owner'; possible values are 'self',
                  'amazon', 'aws-marketplace'; option may be specified
                  multiple times
    -v virt_type: virtualization type (default is PV)

When creating a new AMI, the argument list may include:
        i-<id>          : the instance-id from which to create an image
                          (you need to make sure it is not running)
        aki-<id>        : the AKI to use; this is required if the
                          virtualization type is PV
        ari-<id>        : the ARI to use (optional)
        <arch>          : this is either i386 or x86_64
        name=<ami_name> : the AMI name (required)
        root=<device>   : specifies the root device; can be a simple device
                          name (example: sda1), or a device path (example:
                          /dev/sda1)
        bdm_spec        : the block-device-map spec has the form:
                                dev=<snap-id>[:<dot>]
                          For example,
                              sdb1=snap-12345678:delete
                          Note that all devices start with 'sd';
                          <dot> can be either 'delete' or 'nodelete'; the
                          default, if not explicitly specified, is 'nodelete'

When creating a new AMI from an instance, other than the instance-id, you
only need to specify a name for it.

When copying an AMI, you need to specify the source region and source AMI id.

Example 1:
    ami -C i-12345678 name=my-new-ami

Example 2:
    ami -C aki-12345678 x86_64 root=sda1 name=my-new-ami sda1=snap-12345678
        """
        self.dispatch(self.__ami_cmd, ln)

