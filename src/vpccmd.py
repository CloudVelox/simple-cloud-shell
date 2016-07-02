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

"""This module contains the implementation of the 'vpc' command
"""

import getopt

import common

from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector


class VPCCommand(common.BaseCommand):

    def __vpc_list_gateways(self, region, vpc_id_list):
        """Implements the list-gateways function of the vpc command
        """
        if vpc_id_list is None:
            # XXX: relax this restriction in the future
            print "-a option does not work yet with -g"
            return
        if len(vpc_id_list) != 1:
            # XXX: relax this restriction in the future
            print "Expecting single vpc-id"
            return
        vpc_conn = self.get_vpc_conn(region)
        filter_list = [('attachment.vpc-id', vpc_id_list[0])]
        gateway_list = vpc_conn.get_all_internet_gateways(filters=filter_list)
        for gateway in gateway_list:
            print gateway.id

    @staticmethod
    def __vpc_display(vpc, disp, pg):
        """Display VPC info
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-14s %-10s %-20s", vpc.id, vpc.state, vpc.cidr_block)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", vpc.id)
            pg.prt("%15s : %s", "State", vpc.state)
            pg.prt("%15s : %s", "CIDR-block", vpc.cidr_block)
            pg.prt("%15s : %s", "DCHP-options", vpc.dhcp_options_id)
            if disp.display_tags:
                common.display_tags(vpc.tags, pg)
        else:
            pg.prt("%s", vpc.id)
            if disp.display_tags:
                common.display_tags(vpc.tags, pg)

    def __vpc_list_cmd(self, region, selector, disp):
        """Implements the list function of the vpc command
        """
        if not selector.has_selection():
            return
        vpc_conn = self.get_vpc_conn(region)
        vpc_list = vpc_conn.get_all_vpcs(
                                vpc_ids=selector.resource_id_list,
                                filters=selector.get_filter_list())
        self.cache_insert(region, [vpc.id for vpc in vpc_list])
        with CommandOutput() as pg:
            for vpc in vpc_list:
                self.__vpc_display(vpc, disp, pg)

    def __vpc_delete_cmd(self, region, vpc_id_list):
        """Implements the list function of the vpc command
        """
        vpc_conn = self.get_vpc_conn(region)
        for vpc_id in vpc_id_list:
            if vpc_conn.delete_vpc(vpc_id):
                self.cache_remove(region, [vpc_id])

    def __vpc_create_cmd(self, region, vpc_args):
        """Implements the list function of the vpc command
        """
        if len(vpc_args) != 1:
            print "Expecting CIDR"
            return
        cidr = vpc_args[0]
        vpc_conn = self.get_vpc_conn(region)
        vpc = vpc_conn.create_vpc(cidr)
        if vpc:
            self.cache_insert(region, [vpc.id])
            print vpc.id

    def __vpc_cmd(self, argv):
        """Implements the vpc command
        """
        cmd_delete = False
        cmd_create = False
        disp = DisplayOptions()
        selector = ResourceSelector()
        region = None
        opt_list, args = getopt.getopt(argv, "aCDf:lq:r:tx")
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
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if cmd_create:
            self.__vpc_create_cmd(region, args)
        elif cmd_delete:
            self.__vpc_delete_cmd(region, args)
        else:
            selector.resource_id_list = args
            self.__vpc_list_cmd(region, selector, disp)

    def do_vpc(self, ln):
        """
        vpc [-a] [-l] [-r region] [-C] [-D] [vpc-id] ...

Options:
    -C          : create a new VPC; a single argument, the VPC CIDR,
                  is expected
    -D          : delete the specified VPC(s)
        """
        self.dispatch(self.__vpc_cmd, ln)
