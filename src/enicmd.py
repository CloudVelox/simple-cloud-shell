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

"""This module contains the implementation of the 'eni' command
"""

import getopt

import common

from common import amazon2localtime
from common import CommandError
from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector
from common import optional


class ENICommand(common.BaseCommand):

    @staticmethod
    def __eni_display(eni, disp, pg):
        """Display eni info
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-14s %-8s %-14s %-18s %-10s",
                    eni.id,
                    eni.status,
                    eni.vpc_id,
                    eni.subnet_id,
                    eni.availability_zone)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", eni.id)
            pg.prt("%15s : %s", "Status", eni.status)
            if eni.description:
                pg.prt("%15s : %s", "Description", eni.description)
            pg.prt("%15s : %s", "MAC", eni.mac_address)
            pg.prt("%15s : %s", "Zone", eni.availability_zone)
            pg.prt("%15s : %s", "VPC", eni.vpc_id)
            pg.prt("%15s : %s", "Subnet", eni.subnet_id)
            pg.prt("%15s : %s", "Req-managed", eni.requester_managed)
            if eni.private_ip_address:
                pg.prt("%15s : %s", "Primary-IP", eni.private_ip_address)
            if eni.private_ip_addresses:
                pg.prt("%15s : %s",
                    "Private-IPs", ", ".join(
                    [x.private_ip_address for x in eni.private_ip_addresses]))
            if eni.groups:
                pg.prt("%15s : %s", "Groups", " ".join(
                        [group.id for group in eni.groups]))
            pg.prt("%15s : %s", "SRC/DST-check", eni.source_dest_check)
            if eni.attachment:
                att = eni.attachment
                pg.prt("%15s : %s", "Instance", optional(att.instance_id))
                pg.prt("%15s : %s", "Device-index", att.device_index)
                pg.prt("%15s : %s", "Attach-time",
                                amazon2localtime(att.attach_time))
                pg.prt("%15s : %s", "DoT", att.delete_on_termination)
            if disp.display_tags:
                common.display_tags(eni.tags, pg)
        else:
            pg.prt("%s", eni.id)
            if disp.display_tags:
                common.display_tags(eni.tags, pg)

    def __eni_list_cmd(self, region, selector, disp):
        """Implements the list function of the eni command
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        eni_list = ec2_conn.get_all_network_interfaces(
                            filters=selector.get_filter_dict())
        self.cache_insert(region, [eni.id for eni in eni_list])
        if selector.resource_id_list:
            disp_eni_list = [eni for eni in eni_list
                                if eni.id in selector.resource_id_list]
        else:
            disp_eni_list = eni_list
        with CommandOutput() as pg:
            for eni in disp_eni_list:
                self.__eni_display(eni, disp, pg)

    def __eni_create_cmd(self, region, description, arg_list):
        """Implements the create function of the eni command
        """
        sg_id_list = []
        subnet_id = None
        private_ip_addr = None
        for arg in arg_list:
            if arg.startswith('subnet-'):
                subnet_id = arg
            elif arg.startswith('sg-'):
                sg_id_list.append(arg)
            else:
                private_ip_addr = arg
        err_list = []
        if subnet_id is None:
            err_list.append("subnet-id must be specified")
        if private_ip_addr is None:
            err_list.append("private IP address must be specified")
        if err_list:
            raise CommandError("\n".join(err_list))
        ec2_conn = self.get_ec2_conn(region)
        eni = ec2_conn.create_network_interface(subnet_id,
                                private_ip_address=private_ip_addr,
                                description=description,
                                groups=sg_id_list if sg_id_list else None)
        self.cache_insert(region, [eni.id,])
        print eni.id

    def __eni_delete_cmd(self, region, eni_id_list):
        """Implements the create function of the eni command
        """
        ec2_conn = self.get_ec2_conn(region)
        for eni_id in eni_id_list:
            ec2_conn.delete_network_interface(eni_id)

    def __eni_attach_cmd(self, region, arg_list):
        """Implements the attach function of the eni command
        """
        instance_id = None
        eni_id = None
        device_index = None
        for arg in arg_list:
            if arg.startswith('i-'):
                instance_id = arg
            elif arg.startswith('eni-'):
                eni_id = arg
            else:
                try:
                    device_index = int(arg)
                except ValueError:
                    print "Bad device index: %s" % (arg,)
                    proceed = False
        err_list = []
        if instance_id is None:
            err_list.append("instance-id must be specified")
        if eni_id is None:
            err_list.append("eni-id must be specified")
        if device_index is None:
            err_list.append("device_index must be specified")
        if err_list:
            raise CommandError("\n".join(err_list))
        ec2_conn = self.get_ec2_conn(region)
        #
        # NB: this API does not return an attachment-id (it should...)
        #
        ec2_conn.attach_network_interface(eni_id, instance_id, device_index)

    def __eni_detach_cmd(self, region, arg_list):
        """Implements the detach function of the eni command
        """
        instance_id = None
        eni_id = None
        for arg in arg_list:
            if arg.startswith('i-'):
                instance_id = arg
            elif arg.startswith('eni-'):
                eni_id = arg
            else:
                print "Unexpected argument: %s" % (arg,)
                proceed = False
        err_list = []
        if instance_id is None:
            err_list.append("instance-id must be specified")
        if eni_id is None:
            err_list.append("eni-id must be specified")
        if err_list:
            raise CommandError("\n".join(err_list))
        ec2_conn = self.get_ec2_conn(region)
        #
        # Find the network interface
        #
        filter_dict = { 'attachment.instance-id' : instance_id }
        eni_list = ec2_conn.get_all_network_interfaces(filters=filter_dict)
        for eni in eni_list:
            if eni.id == eni_id:
                break
        else:
            raise CommandError("%s not attached to %s" % (eni_id, instance_id))
        ec2_conn.detach_network_interface(eni.attachment.id, force=True)

    def __eni_source_dest_check(self, region, source_dest_check, args):
        if not args:
            return
        eni_id = args[0]
        ec2_conn = self.get_ec2_conn(region)
        if not ec2_conn.modify_network_interface_attribute(eni_id,
                "sourceDestCheck", source_dest_check):
            print "Failed to set sourceDestCheck to %s for %s" % \
                        (source_dest_check, eni_id)

    def __eni_cmd(self, argv):
        """Implements the eni command
        """
        cmd_create = False
        cmd_delete = False
        cmd_attach = False
        cmd_detach = False
        cmd_source_dest_check = False
        source_dest_check = None
        description = None
        disp = DisplayOptions()
        selector = ResourceSelector()
        region = None
        opt_list, args = getopt.getopt(argv, "aBCDd:f:i:lPq:r:StXx")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    selector.select_all = True
                elif opt[0] == '-B':
                    cmd_source_dest_check = True
                    source_dest_check = True
                elif opt[0] == '-C':
                    cmd_create = True
                elif opt[0] == '-D':
                    cmd_delete = True
                elif opt[0] == '-d':
                    description = opt[1]
                elif opt[0] == '-f':
                    selector.add_filter_spec(opt[1])
                elif opt[0] == '-i':
                    selector.add_filter("attachment.instance-id", opt[1])
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-P':
                    cmd_source_dest_check = True
                    source_dest_check = False
                elif opt[0] == '-q':
                    selector.add_tag_filter_spec(opt[1])
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-S':
                    cmd_attach = True
                elif opt[0] == '-t':
                    disp.display_tags = True
                elif opt[0] == '-X':
                    cmd_detach = True
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if cmd_create:
            self.__eni_create_cmd(region, description, args)
        elif cmd_delete:
            self.__eni_delete_cmd(region, args)
        elif cmd_attach:
            self.__eni_attach_cmd(region, args)
        elif cmd_detach:
            self.__eni_detach_cmd(region, args)
        elif cmd_source_dest_check:
            self.__eni_source_dest_check(region, source_dest_check, args)
        else:
            selector.resource_id_list = args
            self.__eni_list_cmd(region, selector, disp)

    def do_eni(self, ln):
        """
        eni [std-options] [list-options]

Options:
    -B          : enable source/dest check
    -C          : create a network interface
    -D          : delete a network interface
    -P          : disable source/dest check
    -S          : attach a network interface to an instance
    -X          : detach a network interface from an instance
        """
        self.dispatch(self.__eni_cmd, ln)

