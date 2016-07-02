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

"""This module contains the implementation of the 'sg' command
"""

import getopt

import common

from common import CommandError
from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector


def _make_port_spec(target):
    """Given a target tuple (port, from_port, to_port), return a string
    representing the port (or port range)
    """
    from_port, to_port = target[1], target[2]
    if from_port == to_port:
        return "%s" % (from_port)
    else:
        return "%s-%s" % (from_port, to_port)

def sg_access_map(ip_perm_list):
    """Convert the ip_perm_list into a dictionary where the
    key is the tuple (protocol, port-range) and the value is
    the set of CIDRs that are allowed access for that protocol/port(s).
    """
    access_map = {}
    for ip_perm in ip_perm_list:
        if ip_perm.from_port is not None:
            from_port = int(ip_perm.from_port)
        else:
            from_port = None
        if ip_perm.to_port is not None:
            to_port = int(ip_perm.to_port)
        else:
            to_port = None
        target = (ip_perm.ip_protocol.upper(), from_port, to_port)
        for grant in ip_perm.grants:
            if grant.cidr_ip:
                if grant.cidr_ip.endswith("/32"):
                    grant_id = grant.cidr_ip.split('/', 1)[0]
                else:
                    grant_id = grant.cidr_ip
            elif grant.group_id:
                grant_id = grant.group_id
            else:
                continue
            if target not in access_map:
                access_map[target] = set()
            access_map[target].add(grant_id)
    return access_map


def portrange2str(port_range):
    """port_range is a tuple of 2 ports
    """
    if port_range[1]:
        portstr = "port range %s-%s" % (port_range[0], port_range[1])
    else:
        portstr = "port %s" % (port_range[0],)
    return portstr


class _PortSpec(object):
    """This class handles endpoint specifications
    """
    
    #
    # Note that the protocol names (tcp, udp, etc) are normalized
    # to lower-case. This is because the AWS API require lower case
    # when modifying EC2-related security groups; VPC-related security
    # groups allow both lower and upper case.
    #

    def __init__(self, port_spec):
        """Given a port spec of the form
                <proto>:<per-proto-spec>
        Note that we evaluate the spec when we need to.
        """
        self.__spec = port_spec
        self.__parsed = False
        self.proto = None             # protocol, in upper-case
        self.from_port = None
        self.to_port = None
        self.port_range_set = set()

    @staticmethod
    def make_str(target):
        """target is a tuple (proto, from_port, to_port); xxx_port is a liberal
        term as the meaning of the tuple members is protocol-specific
        (think proto==ICMP)
        """
        proto, from_port, to_port = target
        norm_proto = proto.lower()
        if norm_proto in ['tcp', 'udp']:
            if from_port == to_port:
                s = "%-4s port %s" % (proto, from_port)
            else:
                s = "%-4s port %s-%s" % (proto, from_port, to_port)
        elif norm_proto == 'icmp':
            if from_port != -1:
                s = "%-4s type %s" % (proto, from_port)
            else:
                s = "%-4s" % (proto,)
        else:
            s = "%-4s args %s,%s" % (proto, from_port, to_port)
        return s

    def parse(self, flexible=False):
        """Parse the given spec. Success is silent. Failure results
        in an error message, and raising a CommandError exception.
        """
        if self.__parsed:
            return
        if ':' in self.__spec:
            proto, port_list_str = self.__spec.split(':', 1)
            self.proto = proto.lower()
            if self.proto not in ['tcp', 'udp']:
                if not flexible:
                    raise CommandError("Bad protocol: %s" % (self.proto,))
            port_str_list = port_list_str.split(',')
            for port_str in port_str_list:
                try:
                    if '-' in port_str:
                        from_port_str, to_port_str = port_str.split('-', 1)
                        from_port = int(from_port_str)
                        to_port = int(to_port_str)
                    else:
                        from_port = to_port = int(port_str)
                    port_range = (from_port, to_port)
                    self.port_range_set.add(port_range)
                except ValueError:
                    raise CommandError("Bad port number: %s" % (port_str,))
        else:
            self.proto = self.__spec.lower()
            # Verify the protocol, but only when authorizing; we allow
            # the 'revoke' functionality to specify anything so that
            # we can do clean-up.
            if self.proto != 'icmp':
                if not flexible:
                    raise CommandError("Bad protocol: %s" % (self.proto,))
        self.__parsed = True


class SGCommand(common.BaseCommand):

    def __sg_display(self, sg, disp, pg):
        """Display all security group info
        """
        if disp.display == DisplayOptions.LONG:
            access_map = sg_access_map(sg.rules)
            out_str = "%-12s %-20s" % (sg.id, sg.name)
            for target in access_map:
                out_str += " %s:%s:%s" % (target[0], _make_port_spec(target),
                                        ",".join(list(access_map[target])))
            pg.prt("%s", out_str)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", sg.id)
            pg.prt("%15s : %s", "Name", sg.name)
            pg.prt("%15s : %s", "Description", sg.description)
            pg.prt("%15s : %s", "Owner", sg.owner_id)
            access_map = sg_access_map(sg.rules)
            for target in access_map:
                pg.prt("%15s : %-22s from %s",
                                        "In-rule",
                                        _PortSpec.make_str(target),
                                        ",".join(list(access_map[target])))
            if disp.display_tags:
                common.display_tags(sg.tags, pg)
        else:
            pg.prt("%s", sg.id)
            if disp.display_tags:
                common.display_tags(sg.tags, pg)

    def __sg_list_cmd(self, region, selector, disp):
        """List security groups
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        sg_list = ec2_conn.get_all_security_groups(
                                        group_ids=selector.resource_id_list,
                                        filters=selector.get_filter_dict())
        self.cache_insert(region, [sg.id for sg in sg_list])
        with CommandOutput() as pg:
            if disp.display_count:
                print "SG count: %d" % (len(sg_list),)
            else:
                for sg in sg_list:
                    self.__sg_display(sg, disp, pg)

    def __sg_revoke_all(self, ec2_conn, sg_id, port_spec):
        """Revoke access to the specified protocol port range to
        all CIDRs and groups.
        """
        sg_list = ec2_conn.get_all_security_groups(group_ids=[sg_id])
        sg = sg_list[0]
        access_map = sg_access_map(sg.rules)
        key = (port_spec.proto, port_spec.from_port, port_spec.to_port)
        if key not in access_map:
            print "The specified proto/port(s) are not " \
                        "in the security group rules"
            return
        principal_set = access_map[key]
        for principal in principal_set:
            print "Revoking access on", principal
            for port_range in port_spec.port_range_set:
                if principal.startswith("sg-"):
                    _ = ec2_conn.revoke_security_group(group_id=sg_id,
                                ip_protocol=port_spec.proto,
                                from_port=port_range[0],
                                to_port=port_range[1],
                                src_security_group_group_id=principal)
                else:
                    _ = ec2_conn.revoke_security_group(group_id=sg_id,
                                ip_protocol=port_spec.proto,
                                from_port=port_range[0],
                                to_port=port_range[1],
                                cidr_ip=principal)
        return True

    def __sg_parse_subnet_spec(self, subnet_spec):
        """Given a subnet_spec which is a string of comma-separated
        CIDRs or simple IP addresses, return a list of CIDRs (simple
        IP addresses become CIDRs by appending /32 to them)
        """
        cidr_list = []
        if not subnet_spec:
            return cidr_list
        for spec in subnet_spec.split(','):
            if '/' in spec:
                cidr_list.append(spec)
            else:
                cidr_list.append(spec + '/32')
        return cidr_list

    def __sg_authorize_cmd(self, region, authorize, args,
                        port_spec, subnet_spec, principal_sg_id):
        """Implements the 'sg -A/-R' command functionality
        """
        if not args:
            raise CommandError("expecting sg-id")
        elif len(args) != 1:
            raise CommandError("expecting a single sg-id")
        if port_spec is None:
            raise CommandError("No port specified")
        sg_id = args[0]
        # We allow the 'revoke' functionality to specify anything so that
        # we can do clean-up.
        port_spec.parse(flexible=False if authorize else True)
        cidr_list = self.__sg_parse_subnet_spec(subnet_spec)
        ec2_conn = self.get_ec2_conn(region)
        complete_success = True
        if authorize:
            if not (cidr_list or principal_sg_id):
                raise CommandError(
                        "You need to specify either a CIDR/IP or "
                            "another security group")
            for port_range in port_spec.port_range_set:
                if principal_sg_id:
                    success = ec2_conn.authorize_security_group(group_id=sg_id,
                                ip_protocol=port_spec.proto,
                                from_port=port_range[0],
                                to_port=port_range[1],
                                src_security_group_group_id=principal_sg_id,
                                )
                    if not success:
                        print "Failed to allow access to %s from SG %s" % \
                                (portrange2str(port_range), principal_sg_id)
                        complete_success = False
                for cidr in cidr_list:
                    success = ec2_conn.authorize_security_group(group_id=sg_id,
                                ip_protocol=port_spec.proto,
                                from_port=port_range[0],
                                to_port=port_range[1],
                                cidr_ip=cidr
                                )
                    if not success:
                        print "Failed to allow access to %s from %s" % \
                                (portrange2str(port_range), cidr)
                        complete_success = False
        else: # revoke
            if cidr_list or principal_sg_id:
                for port_range in port_spec.port_range_set:
                    if principal_sg_id:
                        success = ec2_conn.revoke_security_group(group_id=sg_id,
                                ip_protocol=port_spec.proto,
                                from_port=port_range[0],
                                to_port=port_range[1],
                                src_security_group_group_id=principal_sg_id,
                                )
                        if not success:
                            print "Failed to revoke access to %s from SG %s" %\
                                (portrange2str(port_range), principal_sg_id)
                            complete_success = False
                    for cidr in cidr_list:
                        success = ec2_conn.revoke_security_group(group_id=sg_id,
                                ip_protocol=port_spec.proto,
                                from_port=port_range[0],
                                to_port=port_range[1],
                                cidr_ip=cidr
                                )
                        if not success:
                            print "Failed to revoke access to %s from SG %s" %\
                                (portrange2str(port_range), principal_sg_id)
                            complete_success = False
            else:
                complete_success = self.__sg_revoke_all(ec2_conn,
                                                        sg_id, port_spec)
        if not complete_success:
            if authorize:
                print "Failed to authorize access"
            else:
                print "Failed to revoke access"

    def __sg_create_cmd(self, region, vpc_id, args):
        """Implements the 'sg -C' command functionality
        """
        if len(args) != 2:
            raise CommandError(
                "Expecting security-group-name and security-group-description")
        sg_name = args[0]
        sg_desc = args[1]
        ec2_conn = self.get_ec2_conn(region)
        sg = ec2_conn.create_security_group(sg_name, sg_desc, vpc_id=vpc_id)
        print "Created %s" % (sg.id,)
        self.cache_insert(region, [sg.id])

    def __sg_delete_cmd(self, region, sg_id_list):
        """Implements the 'sg -D' command functionality
        """
        ec2_conn = self.get_ec2_conn(region)
        for sg_id in sg_id_list:
            if ec2_conn.delete_security_group(group_id=sg_id):
                self.cache_remove(region, [sg_id])

    def __sg_cmd(self, argv):
        """Implements the sg command
        """
        cmd_authorize = False
        cmd_revoke = False
        cmd_delete = False
        cmd_create = False
        selector = ResourceSelector()
        disp = DisplayOptions()
        region = None
        subnet_spec = None
        port_spec = None
        principal_sg_id = None
        vpc_id = None   # used when creating a SG
        opt_list, args = getopt.getopt(argv, "aACDf:g:kln:p:q:Rr:s:tv:x")
        for opt in opt_list:
            if opt[0] == '-A':
                cmd_authorize = True
            elif opt[0] == '-C':
                cmd_create = True
            elif opt[0] == '-D':
                cmd_delete = True
            elif opt[0] == '-a':
                selector.select_all = True
            elif opt[0] == '-f':
                selector.add_filter_spec(opt[1])
            elif opt[0] == '-g':
                principal_sg_id = opt[1]
            elif opt[0] == '-k':
                disp.display_count = True
            elif opt[0] == '-l':
                disp.display = DisplayOptions.LONG
            elif opt[0] == '-n':
                selector.add_filter('group-name', opt[1])
            elif opt[0] == '-p':
                port_spec = _PortSpec(opt[1])
            elif opt[0] == '-q':
                selector.add_tag_filter_spec(opt[1])
            elif opt[0] == '-R':
                cmd_revoke = True
            elif opt[0] == '-r':
                region = opt[1]
            elif opt[0] == '-s':
                subnet_spec = opt[1]
            elif opt[0] == '-t':
                disp.display_tags = True
            elif opt[0] == '-v':
                selector.add_filter('vpc-id', opt[1])
                vpc_id = opt[1]
            elif opt[0] == '-x':
                disp.display = DisplayOptions.EXTENDED
        if cmd_authorize:
            self.__sg_authorize_cmd(region, True, args,
                                port_spec, subnet_spec, principal_sg_id)
        elif cmd_revoke:
            self.__sg_authorize_cmd(region, False, args,
                                port_spec, subnet_spec, principal_sg_id)
        elif cmd_delete:
            self.__sg_delete_cmd(region, args)
        elif cmd_create:
            self.__sg_create_cmd(region, vpc_id, args)
        else:
            selector.resource_id_list = args
            self.__sg_list_cmd(region, selector, disp)

    def do_sg(self, ln):
        """
        sg [std-options] [list-options] [-v vpc] [change-options] [sg-id] ...

The options to create/delete a security group are -C/-D respectively.

    -C            : create a new security group; the expected arguments
                    are (1) the security group name, and (2) the security group
                    description
    -D            : delete an existing security group

The options to modify an existing security group are:

    -A            : authorize access
    -R            : revoke access
    -p port-spec  : port-spec in the form <proto>[:port-range-list] where
                    port-range-list is in the form port-range[,port-range]
                    and port-range is in the form port[-port]; example:
                        tcp:22,1024-2047,2049
    -g sg-id      : allow/revoke access to this security group
    -s cidr_list  : allow/revoke access to the CIDRs in this list; this is a
                    comma-separated list of CIDRs or simple IP addresses
                    (which imply a '/32' CIDR)

When revoking access, one does not need to specify the -g/-s options; if none
of these option is specified, access is revoked for all CIDRs and sg-id's
for the particular port-spec.

When creating a new security group, make sure that you use the -v option
to specify a VPC-id if you plan to use the security group for instances
running in  particular VPC.

Example:
        sg -A -p tcp:443,80 -s 0.0.0.0/0 sg-12345678
        """
        self.dispatch(self.__sg_cmd, ln)

