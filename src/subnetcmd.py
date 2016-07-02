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

"""This module contains the implementation of the 'subnet' command
"""

import getopt

import common

from common import CommandError
from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector


class SubnetCommand(common.BaseCommand):

    @staticmethod
    def __subnet_display(subnet, disp, pg):
        """Display subnet info
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-20s %-8s %-18s %-4s %-12s",
                    subnet.id, subnet.state, subnet.cidr_block,
                    subnet.available_ip_address_count,
                    subnet.availability_zone)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", subnet.id)
            pg.prt("%15s : %s", "State", subnet.state)
            pg.prt("%15s : %s", "CIDR-block", subnet.cidr_block)
            pg.prt("%15s : %s", "Avail-IP", subnet.available_ip_address_count)
            pg.prt("%15s : %s", "Zone", subnet.availability_zone)
            pg.prt("%15s : %s", "VPC", subnet.vpc_id)
            if disp.display_tags:
                common.display_tags(subnet.tags, pg)
        else:
            pg.prt("%s", subnet.id)
            if disp.display_tags:
                common.display_tags(subnet.tags, pg)

    def __subnet_list_cmd(self, region, selector, disp):
        """Implements the list function of the subnet command
        """
        if not selector.has_selection():
            return
        vpc_conn = self.get_vpc_conn(region)
        subnet_list = vpc_conn.get_all_subnets(
                                subnet_ids=selector.resource_id_list,
                                filters=selector.get_filter_list())
        self.cache_insert(region, [subnet.id for subnet in subnet_list])
        with CommandOutput() as pg:
            for subnet in subnet_list:
                self.__subnet_display(subnet, disp, pg)

    def __subnet_create_cmd(self, region, vpc_id, args):
        """Implements the subnet creation functionality of the subnet command
        The expected arguments are the VPC-id, the zone and the CIDR. 
        """
        zone = None
        cidr = None
        for arg in args:
            if arg.startswith('vpc-'):
                vpc_id = arg
            elif '/' in arg:
                cidr = arg
            elif '-' in arg:
                zone = arg
            else:
                print "Unexpected argument: %s" % (arg,)
                proceed = False
        err_list = []
        if zone is None:
            err_list.append("No zone specified")
        if cidr is None:
            err_list.append("No CIDR specified")
        if vpc_id is None:
            err_list.append("No VPC specified")
        if err_list:
            raise CommandError("\n".join(err_list))
        vpc_conn = self.get_vpc_conn(region)
        subnet = vpc_conn.create_subnet(vpc_id, cidr, zone)
        self.cache_insert(region, [subnet.id])
        print subnet.id

    def __subnet_delete_cmd(self, region, subnet_id_list):
        """Implements the subnet deletion functionality of the subnet command
        The expected arguments are the VPC-id, the zone and the CIDR. 
        """
        vpc_conn = self.get_vpc_conn(region)
        for subnet_id in subnet_id_list:
            if vpc_conn.delete_subnet(subnet_id):
                self.cache_remove(region, [subnet_id])

    def __subnet_cmd(self, argv):
        """Implements the subnet command
        """
        cmd_create = False
        cmd_delete = False
        selector = ResourceSelector()
        disp = DisplayOptions()
        region = None
        opt_list, args = getopt.getopt(argv, "aCDf:lq:r:xtv:")
        vpc_id = None
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    selector.select_all = True
                elif opt[0] == '-C':
                    cmd_create = True
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
                elif opt[0] == '-t':
                    disp.display_tags = True
                elif opt[0] == '-v':
                    vpc_id = opt[1]
                    selector.add_filter('vpc-id', vpc_id)
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if cmd_create:
            # the vpc-id may be specified via option, or as an argument
            self.__subnet_create_cmd(region, vpc_id, args)
        elif cmd_delete:
            self.__subnet_delete_cmd(region, args)
        else:
            selector.resource_id_list = args
            self.__subnet_list_cmd(region, selector, disp)

    def do_subnet(self, ln):
        """
        subnet [std-options] [list-options] [-v vpc_id] [-C] [-D]

The -v option displays the subnets of the specified vpc-id.

The -C option is used to create a subnet; the expected arguments are
    vpc-id, CIDR, zone
in any order.

The -D option is used to delete subnets; the expected arguments are subnet ids.
        """
        self.dispatch(self.__subnet_cmd, ln)

