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

"""This module contains the implementation of the 'eip' command
"""

import getopt

import common

from common import CommandError
from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector
from common import optional


class EIPCommand(common.BaseCommand):
    """Implements the 'eip' command
    """

    @staticmethod
    def __eip_display(address, disp, pg):
        """Display info about the specified address
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-16s %-10s %-12s %-16s %s",
                    address.public_ip,
                    address.domain,
                    optional(address.instance_id),
                    optional(address.private_ip_address),
                    optional(address.allocation_id)
                    )
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", address.public_ip)
            pg.prt("%15s : %s", "Domain", address.domain)
            if address.instance_id:
                pg.prt("%15s : %s", "Instance", address.instance_id)
            if address.allocation_id:
                pg.prt("%15s : %s", "Allocation", address.allocation_id)
            if address.association_id:
                pg.prt("%15s : %s", "Association", address.association_id)
            if address.network_interface_id:
                pg.prt("%15s : %s", "Interface", address.network_interface_id)
            if address.private_ip_address:
                pg.prt("%15s : %s", "Private-IP", address.private_ip_address)
        else:
            pg.prt("%s", address.public_ip)

    def __eip_list_cmd(self, region, selector, disp):
        """Implements the eip list functionality
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        address_list = ec2_conn.get_all_addresses(
                                        addresses=selector.resource_id_list)
        with CommandOutput() as pg:
            for address in address_list:
                self.__eip_display(address, disp, pg)

    def __eip_allocate(self, region, in_vpc, eip_list):
        """Implements the EIP allocation functionality
        """
        if eip_list:
            print "No arguments expected"
            return
        ec2_conn = self.get_ec2_conn(region)
        domain = "vpc" if in_vpc else None
        address = ec2_conn.allocate_address(domain)
        if in_vpc:
            print "%-16s %-12s" % (address.public_ip, address.allocation_id)
        else:
            print address.public_ip

    @staticmethod
    def __eip_release_one(ec2_conn, address):
        """Release the specified address
        """
        if address.domain == 'vpc':
            res = ec2_conn.release_address(allocation_id=address.allocation_id)
        else:
            res = ec2_conn.release_address(public_ip=address.public_ip)
        if not res:
            print "Failed to release %s" % (address.public_ip,)

    def __eip_release(self, region, eip_list):
        """Implements the EIP release functionality
        """
        ec2_conn = self.get_ec2_conn(region)
        address_list = ec2_conn.get_all_addresses(addresses=eip_list)
        for address in address_list:
            self.__eip_release_one(ec2_conn, address)

    def __eip_associate(self, region, move_address, arg_list):
        """Associate an IP address with an instance.
        arg_list[0] is the EIP (aka public_ip).
        """
        try:
            eip_address = arg_list.pop(0)
        except IndexError:
            raise CommandError("Missing EIP")
        instance_id = None
        eni_id = None
        private_ip = None
        for arg in arg_list:
            if arg.startswith("i-"):
                instance_id = arg
            elif arg.startswith("eni-"):
                eni_id = arg
            else:
                private_ip = arg
        if instance_id is None and eni_id is None:
            raise CommandError(
                "Either an instance-id or an interface id must be specified")
        if instance_id is not None and eni_id is not None:
            raise CommandError(
                        "Either an instance-id or an interface id "
                        "must be specified; not both")
        ec2_conn = self.get_ec2_conn(region)
        address_list = ec2_conn.get_all_addresses(addresses=[eip_address])
        address = address_list[0]
        if address.allocation_id:
            print instance_id, private_ip, eni_id, move_address
            ec2_conn.associate_address(instance_id=instance_id,
                                        allocation_id=address.allocation_id,
                                        private_ip_address=private_ip,
                                        network_interface_id=eni_id,
                                        allow_reassociation=move_address)
        else:
            ec2_conn.associate_address(instance_id=instance_id,
                                        public_ip=address.public_ip,
                                        private_ip_address=private_ip,
                                        network_interface_id=eni_id,
                                        allow_reassociation=move_address)

    def __eip_disassociate(self, region, arg_list):
        """Associate an IP address with an instance
        """
        ec2_conn = self.get_ec2_conn(region)
        address_list = ec2_conn.get_all_addresses(addresses=arg_list)
        for address in address_list:
            if address.association_id:
                ec2_conn.disassociate_address(
                                        association_id=address.association_id)
            else:
                ec2_conn.disassociate_address(public_ip=address.public_ip)

    def __eip_cmd(self, argv):
        """Implements the eip command
        """
        in_vpc = False
        cmd_allocate = False
        cmd_release = False
        cmd_associate = False
        cmd_disassociate = False
        move_address = False
        disp = DisplayOptions()
        selector = ResourceSelector()
        region = None
        opt_list, args = getopt.getopt(argv, "Aaf:lmRr:StXxV")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    selector.select_all = True
                elif opt[0] == '-A':
                    cmd_allocate = True
                elif opt[0] == '-f':
                    selector.add_filter_spec(opt[1])
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-m':
                    move_address = True
                elif opt[0] == '-R':
                    cmd_release = True
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-S':
                    cmd_associate = True
                elif opt[0] == '-t':
                    disp.display_tags = True
                elif opt[0] == '-X':
                    cmd_disassociate = True
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
                elif opt[0] == '-V':
                    in_vpc = True
        if cmd_allocate:
            self.__eip_allocate(region, in_vpc, args)
        elif cmd_release:
            self.__eip_release(region, args)
        elif cmd_associate:
            self.__eip_associate(region, move_address, args)
        elif cmd_disassociate:
            self.__eip_disassociate(region, args)
        else:
            selector.resource_id_list = args
            self.__eip_list_cmd(region, selector, disp)

    def do_eip(self, ln):
        """
        eip [std-options] [list-options] [-A] [-m] [-v] [eip] ...

Options:
    -A          : allocate an elastic IP address
    -R          : release an elastic IP address
    -S          : associate an IP address with an instance
    -X          : disassociate an IP address from an instance
    -m          : move an EIP between the instance's interfaces
    -v          : allocate VPC-suitable address

The -S option expects an EIP address followed by either an instance-id or
a network-interface-id (eni-id), and optionally a private IP address of
the instance.
The -X option expects a list of EIP addresses (can be just one).
        """
        self.dispatch(self.__eip_cmd, ln)

