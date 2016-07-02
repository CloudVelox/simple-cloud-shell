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

"""This module contains the implementation of the 'snap' command
"""

import getopt

import common

from common import amazon2localtime
from common import amazon2unixtime
from common import CommandError
from common import confirm, confirm_aggr
from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector


class SnapCommand(common.BaseCommand):
    """Implementation of the 'snap' command
    """

    def __snap_display(self, snapshot, disp, pg, region):
        """Display snapshot info
        """
        self.cache_insert(region, [snapshot.id])
        if disp.display_size:
            pg.prt("%-14s %4s", snapshot.id, snapshot.volume_size)
        else:
            if disp.display == DisplayOptions.LONG:
                if disp.display_name:
                    last_field = snapshot.tags.get("Name", "-")
                else:
                    last_field = snapshot.description
                pg.prt("%-14s %-10s %6s %4s '%s'",
                    snapshot.id, snapshot.status,
                    amazon2localtime(snapshot.start_time),
                    snapshot.volume_size, last_field)
            elif disp.display == DisplayOptions.EXTENDED:
                pg.prt("%s", snapshot.id)
                pg.prt("%15s : %s", "Status", snapshot.status)
                pg.prt("%15s : %s", "Progress", snapshot.progress)
                pg.prt("%15s : %s", "Description", snapshot.description)
                pg.prt("%15s : %s", "Start-time", 
                                        amazon2localtime(snapshot.start_time))
                pg.prt("%15s : %s", "Size", snapshot.volume_size)
                pg.prt("%15s : %s", "Volume", snapshot.volume_id)
                self.cache_insert(region, [snapshot.volume_id])
                try:
                    snapshot_attr_list = snapshot.get_permissions()
                    for snapshot_attr in snapshot_attr_list:
                        pg.prt("%15s : %s",
                                snapshot_attr, 
                                ", ".join(snapshot_attr_list[snapshot_attr]))
                except Exception, ex:
                    pg.prt("No permissions for %s: %s", snapshot.id, ex)
                if disp.display_tags:
                    common.display_tags(snapshot.tags, pg)
            else:
                pg.prt("%s", snapshot.id)
                if disp.display_tags:
                    common.display_tags(snapshot.tags, pg)

    def __snap_list_cmd(self, region, selector, disp):
        """Implements the list function of the snap command
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        snapshot_list = ec2_conn.get_all_snapshots(
                                snapshot_ids=selector.resource_id_list,
                                owner='self',
                                filters=selector.get_filter_dict())
        snapshot_list = selector.filter_resources(snapshot_list)
        with CommandOutput(output_path=disp.get_output_file()) as pg:
            if disp.display_count:
                if disp.display_size:
                    pg.prt("Snapshot stats: count=%d size=%d",
                        len(snapshot_list),
                        sum([snap.volume_size for snap in snapshot_list]))
                else:
                    pg.prt("Snapshot count: %d", len(snapshot_list))
            else:
                snapshot_list = disp.order_resources(snapshot_list)
                for snapshot in snapshot_list:
                    self.__snap_display(snapshot, disp, pg, region)

    def __snap_create(self, region, description, vol_id_list):
        """Implements the snapshot creation functionality
        """
        ec2_conn = self.get_ec2_conn(region)
        multiple = len(vol_id_list) > 1
        for vol_id in vol_id_list:
            snapshot = ec2_conn.create_snapshot(vol_id, description)
            self.cache_insert(region, [snapshot.id])
            if multiple:
                print snapshot.id, vol_id
            else:
                print snapshot.id

    def __snap_delete(self, region, selector):
        """Implements the snapshot deletion functionality
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        if selector.is_explicit():
            snapshot_id_list = selector.resource_id_list
        else:
            snapshot_list = ec2_conn.get_all_snapshots(owner='self',
                                        filters=selector.get_filter_dict())
            matching_snapshots = selector.filter_resources(snapshot_list)
            snapshot_id_list = [snapshot.id for snapshot in matching_snapshots]
            if not snapshot_id_list:
                return
        if not confirm_aggr("Will delete:", snapshot_id_list):
            return
        for snapshot_id in snapshot_id_list:
            if selector.match_pattern:
                print "Deleting snapshot: %s" % (snapshot_id,)
            ec2_conn.delete_snapshot(snapshot_id)
            self.cache_remove(region, [snapshot_id])

    def __snap_share(self, region, share, args):
        """Implaments the snapshot share/unshare command
        """
        snapshot_id_list = []
        user_ids = []
        for arg in args:
            if arg.startswith("snap-"):
                snapshot_id_list.append(arg)
            else:
                user_ids.append(arg)
        if not snapshot_id_list:
            raise CommandError("No snapshot id specified")
        if not user_ids:
            raise CommandError("No user id(s) specified")
        ec2_conn = self.get_ec2_conn(region)
        snapshot_list = ec2_conn.get_all_snapshots(
                                snapshot_ids=snapshot_id_list)
        if not snapshot_list:
            raise CommandError(
                "Unknown snapshot(s): %s" % (", ".join(snapshot_id_list)))
        for snapshot in snapshot_list:
            try:
                if share:
                    snapshot.share(user_ids=user_ids)
                else:
                    snapshot.unshare(user_ids=user_ids)
            except Exception as ex:
                print "Failed to %s %s: %s" % (
                        "share" if share else "unshare",
                        snapshot.id,
                        ex)

    def __add_display_order(self, disp, order):
        """Add a display order
        """
        for snap_attr in order.split(','):
            if snap_attr.startswith('~'):
                reverse = True
                snap_attr = snap_attr[1:]
            else:
                reverse = False
            if snap_attr == 'size':
                order_pred = lambda snapshot: snapshot.volume_size
            elif snap_attr == 'time':
                order_pred = lambda snapshot: amazon2unixtime(
                                                        snapshot.start_time)
            elif snap_attr == 'status':
                order_pred = lambda snapshot: snapshot.status
            else:
                raise CommandError(
                        "Unknown snapshot attribute: %s" % snap_attr)
            disp.add_display_order(order_pred, reverse)

    def __snap_cmd(self, argv):
        """Implements the snap command
        """
        cmd_create_snapshot = False
        cmd_delete_snapshot = False
        cmd_share_snapshot = False
        cmd_unshare_snapshot = False
        description = None
        disp = DisplayOptions()
        selector = ResourceSelector()
        region = None
        opt_list, args = getopt.getopt(argv, "aCDd:f:klm:nO:o:q:r:SsxtUz:")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    selector.select_all = True
                elif opt[0] == '-C':
                    cmd_create_snapshot = True
                elif opt[0] == '-D':
                    cmd_delete_snapshot = True
                elif opt[0] == '-d':
                    description = opt[1]
                elif opt[0] == '-f':
                    selector.add_filter_spec(opt[1])
                elif opt[0] == '-k':
                    disp.display_count = True
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-m':
                    selector.match_pattern = opt[1]
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
                    cmd_share_snapshot = True
                elif opt[0] == '-s':
                    disp.display_size = True
                elif opt[0] == '-t':
                    disp.display_tags = True
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
                elif opt[0] == '-U':
                    cmd_unshare_snapshot = True
                elif opt[0] == '-z':
                    selector.add_filter('status', opt[1])
        if cmd_create_snapshot:
            self.__snap_create(region, description, args)
        elif cmd_delete_snapshot:
            selector.resource_id_list = args
            self.__snap_delete(region, selector)
        elif cmd_share_snapshot:
            self.__snap_share(region, True, args)
        elif cmd_unshare_snapshot:
            self.__snap_share(region, False, args)
        else:
            selector.resource_id_list = args
            self.__snap_list_cmd(region, selector, disp)

    def do_snap(self, ln):
        """
        snap [std-options] [list-options] [options] [args]

Options:
    -C          : create a snapshot for each of the specified volumes
    -D          : delete snapshot(s)
    -d desc     : snapshot description (when creating a snapshot)
    -k          : displays the snapshot count
    -o order    : the order consists of a comma-separated list
                  of attr_spec where the attr_spec is [~]attr. The
                  available 'attr' values are:
                        size,time,status
                  Example:
                        -o ~size,time
                  orders first by reverse size (i.e. larger first), then
                  by time
    -S          : share a snapshot
    -s          : displays the snapshot size
    -m pattern  : when used with -D, it deletes patterns where the
                  snapshot's Name tag matches the specified pattern;
                  the pattern is a regular expression as per python's
                  re library package
    -U          : unshare a snapshot
    -z status   : show only snapshots with the specified status
                  (pending, completed, error)
        """
        self.dispatch(self.__snap_cmd, ln)

