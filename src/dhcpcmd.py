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

"""This module contains the implementation of the 'dhcp' command
"""

import getopt

import common

from common import CommandError
from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector


class DHCPCommand(common.BaseCommand):
    """Implements the 'dchp' command
    """

    @staticmethod
    def __dhcp_display(dhcp_opt, disp, pg):
        """Display dhcp info
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-20s", dhcp_opt.id)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", dhcp_opt.id)
            for option_name in dhcp_opt.options:
                option_value = dhcp_opt.options[option_name]
                if isinstance(option_value, list):
                    disp_str = ", ".join(option_value)
                else:
                    disp_str = option_value
                pg.prt("%25s : %s", option_name, disp_str)
            if disp.display_tags:
                common.display_tags(dhcp_opt.tags, pg)
        else:
            pg.prt("%s", dhcp_opt.id)
            if disp.display_tags:
                common.display_tags(dhcp_opt.tags, pg)

    def __dhcp_list_cmd(self, region, selector, disp):
        """Implements the list function of the dhcp command
        """
        if not selector.has_selection():
            return
        vpc_conn = self.get_vpc_conn(region)
        dhcp_opt_list = vpc_conn.get_all_dhcp_options(
                                dhcp_options_ids=selector.resource_id_list)
        self.cache_insert(region, [dhcp_opt.id for dhcp_opt in dhcp_opt_list])
        with CommandOutput() as pg:
            for dhcp_opt in dhcp_opt_list:
                self.__dhcp_display(dhcp_opt, disp, pg)

    def __dhcp_delete_cmd(self, region, dhcp_opt_id_list):
        """Implements the delete function of the dhcp command
        """
        vpc_conn = self.get_vpc_conn(region)
        for dhcp_opt_id in dhcp_opt_id_list:
            if vpc_conn.delete_dhcp_options(dhcp_opt_id):
                self.cache_remove(region, [dhcp_opt_id])

    def __dhcp_associate_cmd(self, region, arg_list):
        """Implements the associate function of the dhcp command
        """
        dhcp_opt_id = None
        vpc_id = None
        for arg in arg_list:
            if arg == "default" or arg.startswith("dopt-"):
                dhcp_opt_id = arg
            elif arg.startswith("vpc-"):
                vpc_id = arg
            else:
                raise CommandError("Unexpected argument: %s" % (arg,))
        if vpc_id is None:
            raise CommandError("No VPC ID specified")
        if dhcp_opt_id is None:
            raise CommandError("No DHCP OPT ID specified")
        vpc_conn = self.get_vpc_conn(region)
        vpc_conn.associate_dhcp_options(dhcp_opt_id, vpc_id)

    def __dhcp_cmd(self, argv):
        """Implements the dhcp command
        """
        disp = DisplayOptions()
        selector = ResourceSelector()
        region = None
        cmd_delete = False
        cmd_associate = False
        opt_list, args = getopt.getopt(argv, "aDlr:Stx")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    selector.select_all = True
                elif opt[0] == '-D':
                    cmd_delete = True
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-S':
                    cmd_associate = True
                elif opt[0] == '-t':
                    disp.display_tags = True
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if cmd_delete:
            self.__dhcp_delete_cmd(region, args)
        elif cmd_associate:
            self.__dhcp_associate_cmd(region, args)
        else:
            selector.resource_id_list = args
            self.__dhcp_list_cmd(region, selector, disp)

    def do_dhcp(self, ln):
        """
        dhcp [std-options] [list-options] [-D] [-S]

Options:
    -S dhcp-opt-id vpc-id       : associate dhcp-opt-id with vpc-id; use
                                  'default' to set the DHCP options of the
                                  specified VPC to the default dhcp options
    -D dhcp-opt-id              : delete the specified DHCP options
        """
        self.dispatch(self.__dhcp_cmd, ln)

