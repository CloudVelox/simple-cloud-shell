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

"""This module contains the implementation of the 'vol' command
"""

import getopt
import time

import common

from common import amazon2localtime
from common import amazon2unixtime
from common import CommandError
from common import confirm
from common import confirm_aggr
from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector

class VolCommand(common.BaseCommand):
    """Implementation of the 'vol' command
    """

    def __vol_display(self, vol, disp, pg, region):
        """Display volume info
        """
        self.cache_insert(region, [vol.id])
        if disp.display_size:
            pg.prt("%-14s %4s", vol.id, vol.size)
        else:
            if disp.display == DisplayOptions.LONG:
                snapshot_id = vol.snapshot_id.strip()
                if not snapshot_id:
                    snapshot_id = '-'
                pg.wrt("%-14s %-10s %-12s %4s %-14s",
                        vol.id, vol.status, vol.zone, vol.size, snapshot_id)
                if vol.snapshot_id:
                    self.cache_insert(region, [vol.snapshot_id])
                if vol.attach_data and vol.attach_data.instance_id:
                    attach_str = "%s:%s" % (vol.attach_data.instance_id,
                                                vol.attach_data.device)
                else:
                    attach_str = "-"
                pg.wrt(" %-22s", attach_str)
                if disp.display_name:
                    vol_name = vol.tags.get("Name")
                    if vol_name:
                        pg.wrt(" %s", vol_name)
                pg.wrt("\n")
            elif disp.display == DisplayOptions.EXTENDED:
                pg.prt("%s", vol.id)
                pg.prt("%15s : %s", "Status", vol.status)
                pg.prt("%15s : %s", "Size", vol.size)
                pg.prt("%15s : %s", "Creation-time",
                                        amazon2localtime(vol.create_time))
                if vol.snapshot_id:
                    pg.prt("%15s : %s", "Snapshot", vol.snapshot_id)
                    self.cache_insert(region, [vol.snapshot_id])
                pg.prt("%15s : %s", "Zone", vol.zone)
                pg.prt("%15s : %s", "Type", vol.type)
                if vol.iops:
                    pg.prt("%15s : %s", "IOPS", vol.iops)
                if vol.attach_data:
                    atd = vol.attach_data
                    if atd.instance_id:
                        pg.prt("%15s : %s", "Instance-id", atd.instance_id)
                    if atd.device:
                        pg.prt("%15s : %s", "Device", atd.device)
                    if atd.status:
                        pg.prt("%15s : %s", "Attach-status", atd.status)
                    if atd.attach_time:
                        pg.prt("%15s : %s", "Attach-time",
                                        amazon2localtime(atd.attach_time))
                if disp.display_tags:
                    common.display_tags(vol.tags, pg)
            else:
                pg.prt("%s", vol.id)
                if disp.display_tags:
                    common.display_tags(vol.tags, pg)

    def __vol_list_cmd(self, region, selector, disp):
        """Implements the list function of the vol command
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        vol_list = ec2_conn.get_all_volumes(
                                        volume_ids=selector.resource_id_list,
                                        filters=selector.get_filter_dict())
        # Key: volume-status
        # Value: volume-list
        vol_use_map = {}
        with CommandOutput(output_path=disp.get_output_file()) as pg:
            #
            # We either display aggregate volume info, or
            # per-volume info.
            #
            if not disp.display_count:
                vol_list = disp.order_resources(vol_list)
                for vol in vol_list:
                    self.__vol_display(vol, disp, pg, region)
            else:
                for vol in vol_list:
                    if vol.status not in vol_use_map:
                        vol_use_map[vol.status] = []
                    vol_use_map[vol.status].append(vol)
                if disp.display_size:
                    pg.prt("Volume count: %d size=%d",
                                len(vol_list),
                                sum([vol.size for vol in vol_list]))
                else:
                    pg.prt("Volume count: %d", len(vol_list))
                for vol_status in vol_use_map:
                    if disp.display_size:
                        pg.prt("%20s : %d size=%d",
                            vol_status, len(vol_use_map[vol_status]),
                            sum([vol.size for vol in vol_use_map[vol_status]]))
                    else:
                        pg.prt("%20s : %d",
                            vol_status, len(vol_use_map[vol_status]))
                instance_use_map = {}
                unaccounted_vols = []
                for vol in vol_use_map.get('in-use', []):
                    attach_data = vol.attach_data
                    if attach_data:
                        instance_id = attach_data.instance_id
                        if instance_id:
                            if instance_id not in instance_use_map:
                                instance_use_map[instance_id] = []
                            instance_use_map[instance_id].append(vol)
                        else:
                            unaccounted_vols.append(vol)
                    else:
                        unaccounted_vols.append(vol)
                pg.prt("Volumes by instance")
                #
                # Create a list of (#-vols, instance-id)
                #
                vols_by_instance = []
                for instance_id in instance_use_map:
                    tpl = (len(instance_use_map[instance_id]), instance_id)
                    vols_by_instance.append(tpl)
                vols_by_instance.sort(reverse=True)
                for tpl in vols_by_instance:
                    pg.prt("%20s : %d", tpl[1], tpl[0])
                if unaccounted_vols:
                    pg.prt("%20s : %d", "Unaccounted", len(unaccounted_vols))

    def __vol_detach_cmd(self, region, instance_id, selector):
        """Implements the volume detach functionality
        """
        vol_id_list = []
        arg_list = selector.resource_id_list
        for arg in arg_list:
            if arg.startswith("i-"):
                instance_id = arg
            elif arg.startswith("vol-"):
                vol_id_list.append(arg)
        ec2_conn = self.get_ec2_conn(region)
        if not vol_id_list:
            volume_list = ec2_conn.get_all_volumes(
                                filters=selector.get_filter_dict())
            matching_volumes = selector.filter_resources(volume_list)
            vol_id_list = [vol.id for vol in matching_volumes]
            if not vol_id_list:
                return
        if not confirm_aggr("Will detach:", vol_id_list):
            return
        for vol_id in vol_id_list:
            ec2_conn.detach_volume(vol_id, instance_id=instance_id)

    def __vol_create_cmd(self, region, vol_type, args):
        """Implements the volume creation functionality
        """
        n_args = len(args)
        if n_args not in [2, 3]:
            print "Expected arguments: zone [snapshot-id] [size]"
            return
        zone = args.pop(0)
        if not self.is_valid_zone(region, zone):
            raise CommandError(
                "Bad zone: %s\n" % (zone,) +
                "Valid zones are: %s" % (
                        ", ".join(self.get_valid_zone_names(region)),))
        vol_type = vol_type or 'gp2'
        if vol_type in ['standard', 'gp2', 'io1']:
            vol_iops = None
        elif vol_type.startswith('io1:'):
            fields = vol_type.split(':', 1)
            try:
                vol_type = fields[0]
                vol_iops = int(fields[1])
            except:
                raise CommandError("Bad volume type: " + vol_type)
        else:
            raise CommandError("Bad volume type: " + vol_type)
        vol_size = None
        snapshot_id = None
        for arg in args:
            if arg.startswith("snap-"):
                snapshot_id = arg
            else:
                try:
                    vol_size = int(arg)
                except ValueError:
                    raise CommandError("Bad argument: %s" % (arg,))
        ec2_conn = self.get_ec2_conn(region)
        volume = ec2_conn.create_volume(size=vol_size,
                                        zone=zone, snapshot=snapshot_id,
                                        volume_type=vol_type,
                                        iops=vol_iops)
        self.cache_insert(region, [volume.id])
        print volume.id

    def __vol_delete_cmd(self, region, selector):
        """Implements the volume deletion functionality
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        if selector.is_explicit():
            vol_id_list = selector.resource_id_list
        else:
            volume_list = ec2_conn.get_all_volumes(
                                volume_ids=selector.resource_id_list,
                                filters=selector.get_filter_dict())
            matching_volumes = selector.filter_resources(volume_list)
            vol_id_list = [vol.id for vol in matching_volumes]
            if not vol_id_list:
                return
        if not confirm_aggr("Will delete:", vol_id_list):
            return
        for vol_id in vol_id_list:
            ec2_conn.delete_volume(vol_id)
            self.cache_remove(region, [vol_id])

    def __vol_attach_cmd(self, region, args):
        """Implements the volume attach functionality
        """
        device_path = None
        instance_id = None
        volume_id = None
        for arg in args:
            if arg.startswith('vol-'):
                volume_id = arg
            elif arg.startswith('i-'):
                instance_id = arg
            else:
                device_path = arg
        if device_path is None:
            raise CommandError("No device path specified")
        if instance_id is None:
            raise CommandError("No instance-id specified")
        if volume_id is None:
            raise CommandError("No volume-id specified")
        ec2_conn = self.get_ec2_conn(region)
        ec2_conn.attach_volume(volume_id, instance_id, device_path)

    def __vol_detach_sync(self, ec2_conn, vol):
        """Synchronously detach a volume
        """
        print "Detaching volume %s from instance %s" % (vol.id,
                                            vol.attach_data.instance_id)
        ec2_conn.detach_volume(vol.id, instance_id=vol.attach_data.instance_id)
        while True:
            time.sleep(2)
            vol.update()
            if vol.status == 'available':
                return

    def __vol_move_cmd(self, region, args):
        """Implements the volume move functionality
        """
        device_path = None
        instance_id = None
        volume_id = None
        for arg in args:
            if arg.startswith('vol-'):
                volume_id = arg
            elif arg.startswith('i-'):
                instance_id = arg
            else:
                device_path = arg
        if device_path is None:
            raise CommandError("No device path specified")
        if instance_id is None:
            raise CommandError("No instance-id specified")
        if volume_id is None:
            raise CommandError("No volume-id specified")
        ec2_conn = self.get_ec2_conn(region)
        vol_list = ec2_conn.get_all_volumes(volume_ids=[volume_id])
        vol = vol_list[0]
        if vol.status == 'in-use':
            if vol.attach_data.instance_id == instance_id:
                print "Volume %s already attached to instance %s at %s" % (
                        vol.id, instance_id, vol.attach_data.device)
                return
            self.__vol_detach_sync(ec2_conn, vol)
        ec2_conn.attach_volume(vol.id, instance_id, device_path)

    def __add_display_order(self, disp, order):
        """Add a display order
        """
        for vol_attr in order.split(','):
            if vol_attr.startswith('~'):
                reverse = True
                vol_attr = vol_attr[1:]
            else:
                reverse = False
            if vol_attr == 'size':
                order_pred = lambda vol: vol.size
            elif vol_attr == 'time':
                order_pred = lambda vol: amazon2unixtime(vol.create_time)
            elif vol_attr == 'status':
                order_pred = lambda vol: vol.status
            else:
                raise CommandError("Unknown volume attribute: %s" % vol_attr)
            disp.add_display_order(order_pred, reverse)

    def __vol_cmd(self, argv):
        """Implements the vol command
        """
        cmd_detach = False
        cmd_attach = False
        cmd_create = False
        cmd_delete = False
        cmd_move = False
        disp = DisplayOptions()
        selector = ResourceSelector()
        region = None
        instance_id = None
        # Volume type, when creating a new volume
        vol_type = None
        opt_list, args = getopt.getopt(argv, "aCc:Df:i:klMnO:o:q:r:SstXxz:")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    selector.select_all = True
                elif opt[0] == '-C':
                    cmd_create = True
                elif opt[0] == '-c':
                    vol_type = opt[1]
                elif opt[0] == '-D':
                    cmd_delete = True
                elif opt[0] == '-f':
                    selector.add_filter_spec(opt[1])
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-i':
                    instance_id = opt[1]
                    selector.add_filter('attachment.instance-id', instance_id)
                elif opt[0] == '-k':
                    disp.display_count = True
                elif opt[0] == '-M':
                    cmd_move = True
                elif opt[0] == '-n':
                    disp.display_name = True
                elif opt[0] == '-O':
                    disp.set_output_file(opt[1])
                elif opt[0] == '-o':
                    self.__add_display_order(disp, opt[1])
                elif opt[0] == '-q':
                    selector.add_tag_filter_spec(opt[1])
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-S':
                    cmd_attach = True
                elif opt[0] == '-s':
                    disp.display_size = True
                elif opt[0] == '-t':
                    disp.display_tags = True
                elif opt[0] == '-X':
                    cmd_detach = True
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
                elif opt[0] == '-z':
                    selector.add_filter('status', opt[1])
        if cmd_detach:
            selector.resource_id_list = args
            self.__vol_detach_cmd(region, instance_id, selector)
        elif cmd_attach:
            self.__vol_attach_cmd(region, args)
        elif cmd_create:
            self.__vol_create_cmd(region, vol_type, args)
        elif cmd_delete:
            selector.resource_id_list = args
            self.__vol_delete_cmd(region, selector)
        elif cmd_move:
            self.__vol_move_cmd(region, args)
        else:
            selector.resource_id_list = args
            self.__vol_list_cmd(region, selector, disp)

    def do_vol(self, ln):
        """Entry point for the vol command
        """
        self.dispatch(self.__vol_cmd, ln)

    def help_vol(self, argv):
        """Provide help info
        """
        _ = argv.pop(0) # pop the first arg, which is 'vol'
        if not argv:
            print """
        vol [std-options] [list-options] [-s] [-X] [-i instance-id] [args]

Options:
    -C             : create a volume
    -c <voltype>   : type of volume; one of
                        'standard' ==> magnetic disk
                        'gp2' ==> SSD
                        'io1:<num>' ==> SSD w/ <num> IOPS
    -D             : delete volume(s)
    -i instance-id : show all the volumes of the specified instance
    -k             : display volume count
    -M             : move a volume between instances
    -o order_list  : the order_list consists of a comma-separated list
                     of attr_spec where the attr_spec is [~]attr. The
                     available 'attr' values are:
                        size,time,status
                     Example:
                        -o ~size,time
                     orders first by reverse size (i.e. larger first), then
                     by time
    -X             : detach the specified volumes
    -S             : attach the specified volume
    -s             : display the volume size
    -z status      : display only volumes with the specified status
                     (creating, available, in-user, deleting, deleted, error)

Use 'help vol create' for information on how to create a volume.
Use 'help vol attach' for information on how to attach a volume.
Use 'help vol move' for information on how to move a volume.
"""
            return
        arg = argv.pop(0)
        if arg == 'create':
            print """
Expected arguments when creating a volume:
    zone
    snapshot-id and/or volume size (number in GB)

The zone is required; at least one of snapshot-id/volume-size must be
specified. Example:

        vol -C us-east-1a 100
"""
        elif arg == 'attach':
            print """
Expected arguments when attaching a volume:
    instance-id
    device path
    volume-id

The arguments can be specified in any order.
Example:

        vol -S i-12345678 vol-abcd1234 /dev/sdf1
"""
        elif arg == 'move':
            print """
Expected arguments when moving a volume:
    instance-id
    device path
    volume-id

The arguments can be specified in any order.
Example:

        vol -M i-12345678 vol-abcd1234 /dev/sdf1
"""
        else:
            print "No help for 'vol %s'" % (arg,)

