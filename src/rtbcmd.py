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

"""This module contains the implementation of the 'rtb' command
"""

import getopt

import common

from common import CommandError
from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector


class RTBCommand(common.BaseCommand):

    @staticmethod
    def __rtb_display(rtb, disp, pg):
        """Display route-table info
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-14s %-10s", rtb.id, rtb.vpc_id)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", rtb.id)
            pg.prt("%15s : %s", "VPC", rtb.vpc_id)
            for route in rtb.routes:
                if route.gateway_id:
                    dest = route.gateway_id 
                else:
                    dest = route.instance_id 
                pg.prt("%15s : %-16s %-12s %s",
                        "Route",
                        route.destination_cidr_block,
                        dest,
                        route.state)
            if disp.display_tags:
                common.display_tags(rtb.tags, pg)
        else:
            pg.prt("%s", rtb.id)
            if disp.display_tags:
                common.display_tags(rtb.tags, pg)

    def __rtb_list_cmd(self, region, selector, disp):
        """Implements the list function of the rtb command
        """
        if not selector.has_selection():
            return
        vpc_conn = self.get_vpc_conn(region)
        rtb_list = vpc_conn.get_all_route_tables(
                        route_table_ids=selector.resource_id_list,
                        filters=selector.get_filter_list())
        self.cache_insert(region, [rtb.id for rtb in rtb_list])
        with CommandOutput() as pg:
            for rtb in rtb_list:
                self.__rtb_display(rtb, disp, pg)

    def __rtb_delete_cmd(self, region, rtb_id_list):
        """Implements the delete function of the rtb command
        """
        vpc_conn = self.get_vpc_conn(region)
        for rtb_id in rtb_id_list:
            if vpc_conn.delete_route_table(rtb_id):
                self.cache_remove(region, [rtb_id])

    def __rtb_add_route_cmd(self, region, arg_list):
        """Implements the add route function of the rtb command
        """
        rtb_id = None
        cidr = None
        instance_id = None
        igw_id = None
        for arg in arg_list:
            if arg.startswith("rtb-"):
                rtb_id = arg
            elif arg.startswith("i-"):
                instance_id = arg
            elif arg.startswith("igw-"):
                igw_id = arg
            elif '/' in arg:    # it's a CIDR
                cidr = arg
            else:
                raise CommandError("Unexpected argument: %s" % (arg,))
        if instance_id and igw_id:
            raise CommandError("You need to specify either an instance id or "
                        "an internet gateway id")
        if rtb_id is None:
            raise CommandError("No route-table id specified")
        if cidr is None:
            raise CommandError("No CIDR specified")
        vpc_conn = self.get_vpc_conn(region)
        vpc_conn.create_route(rtb_id, cidr, igw_id, instance_id)

    def __rtb_delete_route_cmd(self, region, arg_list):
        """Implements the delete route function of the rtb command
        """
        rtb_id = None
        cidr_list = []
        for arg in arg_list:
            if arg.startswith("rtb-"):
                rtb_id = arg
            elif '/' in arg:    # it's a CIDR
                cidr_list.append(arg)
            else:
                raise CommandError("Unexpected argument: %s" % (arg,))
        if rtb_id is None:
            raise CommandError("No route-table id specified")
        vpc_conn = self.get_vpc_conn(region)
        for cidr in cidr_list:
            vpc_conn.delete_route(rtb_id, cidr)

    def __rtb_cmd(self, argv):
        """Implements the rtb command
        """
        disp = DisplayOptions()
        selector = ResourceSelector()
        region = None
        cmd_delete = False
        cmd_delete_route = False
        cmd_add_route = False
        opt_list, args = getopt.getopt(argv, "aDf:lq:r:Stv:Xx")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    selector.select_all = True
                elif opt[0] == '-D':
                    cmd_delete = True
                elif opt[0] == '-f':
                    selector.add_filter_spec(opt[1])
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-q':
                    selector.add_tag_filter_spec(opt[1])
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-S':
                    cmd_add_route = True
                elif opt[0] == '-t':
                    disp.display_tags = True
                elif opt[0] == '-v':
                    vpc_id = opt[1]
                    selector.add_filter('vpc-id', vpc_id)
                elif opt[0] == '-X':
                    cmd_delete_route = True
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if cmd_delete:
            self.__rtb_delete_cmd(region, args)
        elif cmd_add_route:
            self.__rtb_add_route_cmd(region, args)
        elif cmd_delete_route:
            self.__rtb_delete_route_cmd(region, args)
        else:
            selector.resource_id_list = args
            self.__rtb_list_cmd(region, selector, disp)

    def do_rtb(self, ln):
        """
        rtb [std-options] [list-options] [-v vpc-id] [-D] [rtb-id] ...

Options:
    -D          : delete the specified route table(s)
    -S          : add a route to the route table; the arguments are:
                        rtb-id, instance-id or IGW-id, CIDR
    -X          : delete a route from the route table; the argument is
                  the CIDR identifying the route
        """
        self.dispatch(self.__rtb_cmd, ln)

