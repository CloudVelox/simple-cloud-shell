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

"""This module contains the implementation of the 'elb' command
"""

import getopt

import boto

import common

from common import CommandError
from common import DisplayOptions
from common import CommandOutput
from common import optional
from common import amazon2localtime


def _boto_min_version(vers):
    """Returns True if boto_version >= vers
    """
    vers_list = [int(v) for v in vers.split('.')]
    boto_vers_list = [int(v) for v in boto.__version__.split('.')]
    for i in range(len(boto_vers_list)):
        if i > len(vers_list):
            return True
        if boto_vers_list[i] > vers_list[i]:
            return True
        if boto_vers_list[i] < vers_list[i]:
            return False
    return True


class ELBCommand(common.BaseCommand):
    def __elb_display(self, elb, disp, pg, region):
        """Display information about the specified ELB.
        """
        if disp.display_policies:
            pg.prt("%s", elb.name)
            if elb.policies.app_cookie_stickiness_policies:
                for policy in elb.policies.app_cookie_stickiness_policies:
                    pg.prt("%15s : %-15s cookie=%s",
                                "App-cookie",
                                policy.policy_name,
                                policy.cookie_name)
            if elb.policies.lb_cookie_stickiness_policies:
                for policy in elb.policies.lb_cookie_stickiness_policies:
                    pg.prt("%15s : %-15s expiration=%s",
                                "LB-cookie",
                                policy.policy_name,
                                policy.cookie_expiration_period)
        elif disp.display == DisplayOptions.LONG:
            pg.prt("%-20s %-30s %s",
                    elb.name,
                    elb.dns_name,
                    optional(elb.vpc_id))
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", elb.name)
            pg.prt("%15s : %s", "DNS-name", elb.dns_name)
            pg.prt("%15s : %s", "CNAME", elb.canonical_hosted_zone_name)
            pg.prt("%15s : %s", "Create-time",
                            amazon2localtime(elb.created_time))
            for listener in elb.listeners:
                pg.prt("%15s : in=%-4s out=%-4s proto=%-5s",
                                "Listener",
                                listener.load_balancer_port,
                                listener.instance_port,
                                listener.protocol)
                if listener.policy_names:
                    pg.prt("%15s   policy=%s", "", listener.policy_names[0])
                if listener.ssl_certificate_id:
                    cert_name = listener.ssl_certificate_id.split('/', 1)[1]
                    pg.prt("%15s   cert=%s", "", cert_name)
            pg.prt("%15s : %s" % ("Group", elb.source_security_group.name))
            if elb.vpc_id:
                pg.prt("%15s : %s", "VPC-id", elb.vpc_id)
                self.cache_insert(region, [elb.vpc_id])
            if elb.subnets:
                pg.prt("%15s : %s", "Subnets", ", ".join(elb.subnets))
                self.cache_insert(region, elb.subnets)
            if elb.availability_zones:
                pg.prt("%15s : %s", "Zones", ", ".join(elb.availability_zones))
            if elb.health_check:
                pg.prt("%15s : i=%s t=%s ht=%s ut=%s %s",
                                "Healthcheck",
                                elb.health_check.interval,
                                elb.health_check.timeout,
                                elb.health_check.healthy_threshold,
                                elb.health_check.unhealthy_threshold,
                                optional(elb.health_check.target))
            if elb.policies.app_cookie_stickiness_policies:
                for policy in elb.policies.app_cookie_stickiness_policies:
                    pg.prt("%15s : %-15s cookie=%s",
                                "App-cookie",
                                policy.policy_name,
                                policy.cookie_name)
            if elb.policies.lb_cookie_stickiness_policies:
                for policy in elb.policies.lb_cookie_stickiness_policies:
                    pg.prt("%15s : %-15s expiration=%s",
                                "LB-cookie",
                                policy.policy_name,
                                policy.cookie_expiration_period)
            if elb.instances:
                for instance_info in elb.instances:
                    pg.prt("%15s : %-12s", "Instance", instance_info.id)
                    self.cache_insert(region, [instance_info.id])
        else:
            pg.prt("%s", elb.name)

    def __elb_list_cmd(self, region, elb_names, disp):
        """Implement the list functionality of the elb command
        """
        elb_conn = self.get_elb_conn(region)
        elb_list = elb_conn.get_all_load_balancers(
                                        load_balancer_names=elb_names)
        with CommandOutput() as pg:
            for elb in elb_list:
                self.__elb_display(elb, disp, pg, region)

    @staticmethod
    def __elb_parse_listeners(listener_spec_list):
        """Convert a list of listener specs to a list of listeners
        suitable to use in the boto API. A listener spec looks like this:
                lb_port,instance_port,lb_proto,instance_proto[,cert-arn]
        """
        if not _boto_min_version('2.9.9'):
            raise CommandError(
                "This command requires at least boto version 2.9.9")
        listener_list = []
        for spec in listener_spec_list:
            fields = spec.split(',')
            n_fields = len(fields)
            if n_fields not in [4, 5]:
                raise CommandError("Bad ELB listener spec: %s" % (spec,))
            try:
                lb_port = int(fields[0])
                instance_port = int(fields[1])
                lb_proto = fields[2].upper()
                instance_proto = fields[3].upper()
            except ValueError:
                raise CommandError("Bad port number in %s" % (spec,))
            if lb_proto not in ['HTTP', 'HTTPS', 'TCP']:
                raise CommandError("Bad LB protocol in spec: %s" % (spec,))
            if instance_proto not in ['HTTP', 'HTTPS', 'TCP']:
                raise CommandError(
                    "Bad instance protocol in spec: %s" % (spec,))
            if lb_proto == 'HTTPS':
                if n_fields != 5:
                    raise CommandError(
                        "SSL Certificate ARN is required for %s" % (spec,))
                arn = fields[4]
                listener = (lb_port, instance_port,
                                        lb_proto, instance_proto, arn)
            else:
                listener = (lb_port, instance_port, lb_proto, instance_proto)
            listener_list.append(listener)
        return listener_list

    def __elb_create_cmd(self, region, subnet_list,
                                    listener_spec_list, sg_id_list, args):
        """Create an ELB
        """
        if not subnet_list:
            raise CommandError("No subnets specified")
        if not args:
            raise CommandError("No ELB name specified")
        listener_list = self.__elb_parse_listeners(listener_spec_list)
        if not listener_list:
            raise CommandError("You need to specify at least one listener")
        elb_name = args[0]
        elb_conn = self.get_elb_conn(region)
        elb = elb_conn.create_load_balancer(
                                name=elb_name,
                                zones=None,
                                complex_listeners=listener_list,
                                subnets=subnet_list,
                                security_groups=sg_id_list)
        if elb:
            print elb.dns_name
        else:
            print "ELB creation failed"

    def __elb_delete_cmd(self, region, arg_list):
        """Delete an ELB
        """
        elb_conn = self.get_elb_conn(region)
        for elb_name in arg_list:
            elb_conn.delete_load_balancer(elb_name)

    def __elb_modify_add_cmd(self, region,
                        listener_spec_list, sg_id_list,
                        subnet_list, instance_id_list, args):
        """Modify an existing ELB
        """
        if not args:
            raise CommandError("No ELB specified")
        elb_name = args[0]
        elb_conn = self.get_elb_conn(region)
        if listener_spec_list:
            listener_list = self.__elb_parse_listeners(listener_spec_list)
            if not listener_list:
                raise CommandError("No listeners specified")
            status = elb_conn.create_load_balancer_listeners(
                                name=elb_name,
                                complex_listeners=listener_list)
        if sg_id_list:
            elb_conn.apply_security_groups_to_lb(elb_name, sg_id_list)
        if subnet_list:
            elb_conn.attach_lb_to_subnets(elb_name, subnet_list)
        if instance_id_list:
            elb_conn.register_instances(elb_name, instance_id_list)

    def __elb_modify_remove_cmd(self, region,
                        port_spec_list, sg_id_list,
                        subnet_list, instance_id_list, args):
        """Modify an existing ELB
        """
        if not args:
            raise CommandError("No ELB specified")
        elb_name = args[0]
        elb_conn = self.get_elb_conn(region)
        if port_spec_list:
            try:
                port_list = [int(p) for p in port_spec_list]
            except ValueError, ve:
                raise CommandError(
                    "Bad port specification: %s" % (",".join(port_spec_list)))
            status = elb_conn.delete_load_balancer_listeners(
                                name=elb_name,
                                ports=port_list)
        if sg_id_list:
            print "The ability to unapply security groups to an ELB" \
                        " is not available via boto"
        if subnet_list:
            elb_conn.detach_lb_from_subnets(elb_name, subnet_list)
        if instance_id_list:
            elb_conn.deregister_instances(elb_name, instance_id_list)

    def __elb_instance_health(self, region, args):
        """Report instance health
        """
        if not args:
            raise CommandError("No ELB specified")
        elb_name = args[0]
        elb_conn = self.get_elb_conn(region)
        instance_state_list = elb_conn.describe_instance_health(elb_name)
        for instance_state in instance_state_list:
            print "%-12s %-10s %-6s '%s'" % (
                instance_state.instance_id,
                instance_state.state,
                instance_state.reason_code,
                instance_state.description,)
            self.cache_insert(region, [instance_state.instance_id])

    @staticmethod
    def __parse_healthcheck(healthcheck_spec):
        """Parse a healthcheck specification and return a HealthCheck object.
        The spec looks like this:
                name=value[,name=value]...
        where name is:
            i   : interval
            t   : timeout
            ht  : healthy threshold
            ut  : unhealthy threshold
            l   : link
        """
        spec_list = healthcheck_spec.split(',')
        interval = None
        timeout = None
        healthy_threshold = None
        unhealthy_threshold = None
        link = None
        for spec in spec_list:
            if '=' not in spec:
                raise CommandError(
                        "Bad healthspec: missing '=' in %s" % (spec,))
            name, value = spec.split('=', 1)
            try:
                if name == 'i':
                    if value:
                        interval = int(value)
                elif name == 't':
                    if value:
                        timeout = int(value)
                elif name == 'ht':
                    if value:
                        healthy_threshold = int(value)
                elif name == 'ut':
                    if value:
                        unhealthy_threshold = int(value)
                elif name == 'l':
                    if value:
                        link = value
                else:
                    raise CommandError("Bad healthspec: %s" % (spec,))
            except ValueError:
                raise CommandError(
                        "Expecting an integer value for %s" % (name,))
        healthcheck = boto.ec2.elb.healthcheck.HealthCheck(
                                interval=interval,
                                target=link,
                                timeout=timeout,
                                healthy_threshold=healthy_threshold,
                                unhealthy_threshold=unhealthy_threshold)
        return healthcheck

    def __elb_config_healthcheck(self, region, healthcheck_spec, args):
        """Configure (add) an ELB healthcheck
        """
        healthcheck = self.__parse_healthcheck(healthcheck_spec)
        if not args:
            raise CommandError("No ELB specified")
        elb_name = args[0]
        elb_conn = self.get_elb_conn(region)
        cur_healthcheck = elb_conn.configure_health_check(elb_name, healthcheck)
        print "Healthcheck: i=%s t=%s ht=%s ut=%s %s" % (
                                cur_healthcheck.interval,
                                cur_healthcheck.timeout,
                                cur_healthcheck.healthy_threshold,
                                cur_healthcheck.unhealthy_threshold,
                                optional(cur_healthcheck.target))

    def __elb_policy_add(self, region, policy_name, listener_list, args):
        """Add a policy or associate a policy with a listener
        """
        if not args:
            raise CommandError("No ELB specified")
        elb_name = args.pop(0)
        elb_conn = self.get_elb_conn(region)
        if listener_list:
            lb_port = int(listener_list[0])
            elb_conn.set_lb_policies_of_listener(elb_name, lb_port, policy_name)
        else:
            # Create a new policy
            if not args:
                raise CommandError("No policy type for %s" % (policy_name,))
            policy_type = args.pop(0)
            if policy_type == 'lb-cookie':
                try:
                    cookie_expiration_period = int(args.pop(0))
                except IndexError:
                    raise CommandError("Missing expiration period")
                except ValueError:
                    raise CommandError("Expiration period must be a number")
                elb_conn.create_lb_cookie_stickiness_policy(
                                        cookie_expiration_period, 
                                        elb_name,
                                        policy_name)
            elif policy_type == 'app-cookie':
                try:
                    cookie_name = args.pop(0)
                except IndexError:
                    raise CommandError("Missing cookie name")
                elb_conn.create_app_cookie_stickiness_policy(
                                        cookie_name,
                                        elb_name,
                                        policy_name)
            else:
                raise CommandError("Unknown policy type: " + policy_type)

    def __elb_policy_remove(self, region, policy_name, listener_list, args):
        """Remove a policy or disassociate a policy from a listener
        """
        if not args:
            raise CommandError("No ELB specified")
        elb_name = args.pop(0)
        elb_conn = self.get_elb_conn(region)
        if listener_list:
            lb_port = int(listener_list[0])
            elb_conn.set_lb_policies_of_listener(elb_name, lb_port, [])
        else:
            elb_conn.delete_lb_policy(elb_name, policy_name)

    def __elb_cmd(self, argv):
        """Implements the elb command
        """
        all_elbs = False
        cmd_create_elb = False
        cmd_delete_elb = False
        cmd_modify_add = False
        cmd_modify_remove = False
        cmd_query_instance_health = False
        cmd_config_healthcheck = False
        disp = DisplayOptions()
        disp.display_policies = False
        region = None
        policy_name = None
        healthcheck_spec = None
        subnet_list = []
        listener_list = []
        sg_id_list = []
        instance_id_list = []
        opt_list, args = getopt.getopt(argv, "AaCDg:H:hi:L:lpP:Rr:s:x")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    all_elbs = True
                elif opt[0] == '-A':
                    cmd_modify_add = True
                elif opt[0] == '-C':
                    cmd_create_elb = True
                elif opt[0] == '-D':
                    cmd_delete_elb = True
                elif opt[0] == '-g':
                    sg_id_list.extend(opt[1].split(','))
                elif opt[0] == '-H':
                    healthcheck_spec = opt[1]
                    cmd_config_healthcheck = True
                elif opt[0] == '-h':
                    cmd_query_instance_health = True
                elif opt[0] == '-L':
                    listener_list.append(opt[1])
                elif opt[0] == '-i':
                    instance_id_list.extend(opt[1].split(','))
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-p':
                    disp.display_policies = True
                elif opt[0] == '-P':
                    policy_name = opt[1]
                elif opt[0] == '-R':
                    cmd_modify_remove = True
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-s':
                    subnet_list.extend(opt[1].split(','))
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if cmd_create_elb:
            self.__elb_create_cmd(region, subnet_list,
                                listener_list, sg_id_list, args)
        elif cmd_modify_add:
            if policy_name:
                self.__elb_policy_add(region, policy_name,
                                                        listener_list, args)
            else:
                self.__elb_modify_add_cmd(region, listener_list, sg_id_list,
                        subnet_list, instance_id_list, args)
        elif cmd_modify_remove:
            if policy_name:
                self.__elb_policy_remove(region, policy_name,
                                                        listener_list, args)
            else:
                self.__elb_modify_remove_cmd(region, listener_list, sg_id_list,
                        subnet_list, instance_id_list, args)
        elif cmd_delete_elb:
            self.__elb_delete_cmd(region, args)
        elif cmd_config_healthcheck:
            self.__elb_config_healthcheck(region, healthcheck_spec, args)
        elif cmd_query_instance_health:
            self.__elb_instance_health(region, args)
        else:
            if all_elbs or args:
                self.__elb_list_cmd(region,
                                    None if all_elbs else args,
                                    disp)

    def do_elb(self, ln):
        """
        elb [<options>] [<args>]
Options:
    -a          : all ELBs
    -A          : add a subnet/sg/listener/policy to an ELB
    -C          : create an ELB
    -D          : delete an ELB
    -g sg,sg,.. : apply the specified security group(s) to the ELB
    -H spec     : specify a healthcheck specification; a healthspec has the form
                            name=value[,name=value]...
                  where name is:
                        i   : interval
                        t   : timeout
                        ht  : healthy threshold
                        ut  : unhealthy threshold
                        l   : link
    -h          : query instance health
    -i list     : a comma-separated instance-id list to add/remove to the ELB
                  (action depends on -A/-R option)
    -L spec     : specify a listener; form lbport,instport,lbproto,instproto[,arn]
    -l          : long display
    -P policy   : define a new policy
    -p          : display policies associated with the specified ELB
    -R          : remove a subnet/sg/instance/listener/policy from an ELB
    -s sn,sn,.. : attach ELB to the specified subnet(s)
    -x          : extended output

When creating an ELB, the following information must be provided:
        subnets (via -s option)
        security groups (via -g option)
        listeners (via -L option)

To create a new policy for a load balancer:
        elb -A -P <policy-name> <elb-name> <policy-type> <policy-args>

To attach a policy to a load balancer listener:
        elb -A -P <policy-name> -L <lbport> <elb-name>
        """
        self.dispatch(self.__elb_cmd, ln)

