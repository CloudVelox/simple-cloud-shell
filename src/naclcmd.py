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

"""This module contains the implementation of the 'nacl' command
"""

import getopt

import common

from common import DisplayOptions
from common import CommandOutput


class NACLCommand(common.BaseCommand):

    @staticmethod
    def __nacl_display(network_acl, disp, pg):
        """Display nacl info
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-20s", network_acl.id)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", network_acl.id)
            pg.prt("%15s : %s", "VPC", network_acl.vpc_id)
            pg.prt("%15s : %s", "Default", network_acl.default)
            for entry in network_acl.network_acl_entries:
                rule = "Rule %s" % entry.rule_number
                if entry.protocol == -1:
                    proto_spec = "ALL"
                else:
                    proto_spec = "%s:%s-%s" % (entry.protocol,
                                entry.port_range.from_port,
                                entry.port_range.to_port)
                if entry.egress:
                    direction = "egress"
                else:
                    direction = "ingress"
                pg.prt("%15s: %-8s %-10s %-20s %s ",
                            rule, direction, entry.rule_action,
                            proto_spec, entry.cidr_block)
            for assoc in network_acl.associations:
                pg.prt("%15s: %s", "Subnet", assoc.subnet_id)
            if disp.display_tags:
                common.display_tags(network_acl.tags, pg)
        else:
            pg.prt("%s", network_acl.id)
            if disp.display_tags:
                common.display_tags(network_acl.tags, pg)

    def __nacl_list_cmd(self, region, network_acl_id_list, disp):
        """Implements the list function of the nacl command
        """
        vpc_conn = self.get_vpc_conn(region)
        network_acl_list = vpc_conn.get_all_network_acls(
                                network_acl_ids=network_acl_id_list)
        self.cache_insert(region,
                [network_acl.id for network_acl in network_acl_list])
        with CommandOutput() as pg:
            for network_acl in network_acl_list:
                self.__nacl_display(network_acl, disp, pg)

    def __nacl_cmd(self, argv):
        """Implements the nacl command
        """
        all_network_acls = False
        disp = DisplayOptions()
        region = None
        opt_list, args = getopt.getopt(argv, "alr:tx")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    all_network_acls = True
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-t':
                    disp.display_tags = True
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if False:
            pass
        else:
            if all_network_acls or args:
                self.__nacl_list_cmd(region,
                                        None if all_network_acls else args,
                                        disp)

    def do_nacl(self, ln):
        """
        nacl [std-options] [list-options]
        """
        self.dispatch(self.__nacl_cmd, ln)

