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

"""This module contains the implementation of the 'igw' command
"""

import getopt

import common

from common import CommandError
from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector


class IGWCommand(common.BaseCommand):
    @staticmethod
    def __igw_display(igw, disp, pg):
        """Display internet gateway info
        """
        if disp.display == DisplayOptions.LONG:
            attachment_list = ["%s:%s" % (attachment.vpc_id, attachment.state)
                                for attachment in igw.attachments]
            disp_list = ["%-24s" % (a,) for a in attachment_list]
            pg.prt("%-14s %s", igw.id, " ".join(disp_list))
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", igw.id)
            for attachment in igw.attachments:
                pg.prt("%15s : %s", attachment.vpc_id, attachment.state)
            if disp.display_tags:
                common.display_tags(igw.tags, pg)
        else:
            pg.prt("%s", igw.id)
            if disp.display_tags:
                common.display_tags(igw.tags, pg)

    def __igw_list_cmd(self, region, selector, disp):
        """Implements the list function of the igw command
        """
        if not selector.has_selection():
            return
        vpc_conn = self.get_vpc_conn(region)
        igw_list = vpc_conn.get_all_internet_gateways(
                                internet_gateway_ids=selector.resource_id_list,
                                filters=selector.get_filter_list())
        self.cache_insert(region, [igw.id for igw in igw_list])
        with CommandOutput() as pg:
            for igw in igw_list:
                self.__igw_display(igw, disp, pg)

    def __igw_create_cmd(self, region):
        """Implements the create function of the igw command
        """
        vpc_conn = self.get_vpc_conn(region)
        igw = vpc_conn.create_internet_gateway()
        if igw:
            self.cache_insert(region, [igw.id])

    def __igw_delete_cmd(self, region, igw_id_list):
        """Implements the delete function of the igw command
        """
        vpc_conn = self.get_vpc_conn(region)
        for igw_id in igw_id_list:
            if vpc_conn.delete_internet_gateway(igw_id):
                self.cache_remove(region, [igw_id])

    def __igw_attach_detach_args(self, arg_list):
        """Parse the arguments for the attach/detach commands
        """
        vpc_id = None
        igw_id = None
        for arg in arg_list:
            if arg.startswith("igw-"):
                igw_id = arg
            elif arg.startswith("vpc-"):
                vpc_id = arg
        if vpc_id is None:
            raise CommandError("No VPC ID specified")
        if igw_id is None:
            raise CommandError("No internet-gateway ID specified")
        return (igw_id, vpc_id)

    def __igw_attach_cmd(self, region, arg_list):
        """Implements the attach function of the igw command
        """
        vpc_conn = self.get_vpc_conn(region)
        igw_id, vpc_id = self.__igw_attach_detach_args(arg_list)
        vpc_conn.attach_internet_gateway(igw_id, vpc_id)

    def __igw_detach_cmd(self, region, arg_list):
        """Implements the detach function of the igw command
        """
        vpc_conn = self.get_vpc_conn(region)
        igw_id, vpc_id = self.__igw_attach_detach_args(arg_list)
        vpc_conn.detach_internet_gateway(igw_id, vpc_id)

    def __igw_cmd(self, argv):
        """Implements the igw command
        """
        disp = DisplayOptions()
        selector = ResourceSelector()
        region = None
        cmd_create = False
        cmd_delete = False
        cmd_detach = False
        cmd_attach = False
        opt_list, args = getopt.getopt(argv, "aCDf:lq:rStv:Xx")
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
                elif opt[0] == '-S':
                    cmd_attach = True
                elif opt[0] == '-t':
                    disp.display_tags = True
                elif opt[0] == '-v':
                    vpc_id = opt[1]
                    selector.add_filter('attachment.vpc-id', vpc_id)
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
                elif opt[0] == '-X':
                    cmd_detach = True
        if cmd_create:
            self.__igw_create_cmd(region)
        elif cmd_delete:
            self.__igw_delete_cmd(region, args)
        elif cmd_attach:
            self.__igw_attach_cmd(region, args)
        elif cmd_detach:
            self.__igw_detach_cmd(region, args)
        else:
            selector.resource_id_list = args
            self.__igw_list_cmd(region, selector, disp)

    def do_igw(self, ln):
        """
    igw [std-options] [list-options] [-v vpc-id] [-C] [-D] [-S] [-X] [igw-id]

Options:
    -C          : create an internet gateway (no arguments expected)
    -D          : delete the specified internet gateway(s)
    -S          : attach an internet gateway to a VPC
    -X          : detach an internet gateway from a VPC
        """
        self.dispatch(self.__igw_cmd, ln)

