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

"""This module contains the implementation of the 'inst' command
"""

import base64
import getopt

import common

from common import CommandError
from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector
from common import amazon2localtime
from common import confirm


def _preprocess(instance_list, disp):
    """Preprocess the instance_list according to the disp (which is
    of type DisplayOptions)
    """
    if disp.display == DisplayOptions.LONG and disp.display_name:
        return sorted(instance_list,
                        key=lambda inst: inst.tags.get("Name", "-"))
    else:
        return instance_list


class InstCommand(common.BaseCommand):
    """Implementation of the 'inst' command
    """

    DEFAULT_INSTANCE_TYPE = "m1.small"
    DEFAULT_EBS_OPTIMIZED = False

    def __inst_display(self, instance, disp, pg, region):
        """Display information about the specified instance.
        """
        res_id_list = [instance.id]
        if disp.display == DisplayOptions.LONG:
            if disp.display_name:
                last_field = instance.tags.get("Name", "-")
            else:
                last_field = amazon2localtime(instance.launch_time)
            pg.prt("%-12s %-10s %-12s %-10s %s",
                    instance.id, instance.state,
                    instance.placement,
                    instance.instance_type,
                    last_field)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", instance.id)
            pg.prt("%15s : %-12s", "State", instance.state)
            pg.prt("%15s : %s", "Launch-time", 
                            amazon2localtime(instance.launch_time))
            pg.prt("%15s : %s", "Location", instance.placement)
            pg.prt("%15s : %s %s %s %s", "Hardware",
                                        instance.instance_type,
                                        instance.architecture,
                                        instance.virtualization_type,
                                        instance.hypervisor,
                                        )
            pg.prt("%15s : %s %s %s %s", "Software",
                                        instance.platform,
                                        instance.image_id,
                                        instance.kernel,
                                        instance.ramdisk)
            res_id_list.append(instance.image_id)
            if instance.kernel:
                res_id_list.append(instance.kernel)
            if instance.ramdisk:
                res_id_list.append(instance.ramdisk)
            pg.prt("%15s : %-12s %s", "Root",
                                        instance.root_device_name,
                                        instance.root_device_type)
            pg.prt("%15s : %s", "EBS-optimized",
                        "True" if instance.ebs_optimized else "False")
            if instance.vpc_id:
                pg.prt("%15s : %-14s %-16s", "VPC-info",
                                    instance.vpc_id, instance.subnet_id)
                res_id_list.extend([instance.vpc_id, instance.subnet_id])
            if instance.private_ip_address:
                pg.prt("%15s : %s %s", "IP",
                                        instance.ip_address,
                                        instance.private_ip_address)
            for netif in instance.interfaces:
                pg.prt("%15s : %-15s idx=%-2s %-16s SDC=%s",
                                "Interface",
                                netif.id,
                                netif.attachment.device_index,
                                netif.private_ip_address,
                                "on" if netif.source_dest_check else "off"
                                )
                res_id_list.append(netif.id)
            if instance.groups:
                group_id_list = [group.id for group in instance.groups]
                pg.prt("%15s : %s", "Groups", " ".join(group_id_list))
                res_id_list.extend(group_id_list)
            bdev_list = instance.block_device_mapping.keys()
            bdev_list.sort()
            for bdev in bdev_list:
                bdev_info = instance.block_device_mapping[bdev]
                pg.prt("%15s : %-12s %-12s %s dot=%s",
                        "Device", bdev,
                        bdev_info.volume_id,
                        bdev_info.status,
                        bdev_info.delete_on_termination)
                res_id_list.append(bdev_info.volume_id)
            if disp.display_tags:
                common.display_tags(instance.tags, pg)
        else:
            pg.prt("%s", instance.id)
            if disp.display_tags:
                common.display_tags(instance.tags, pg)
        self.cache_insert(region, res_id_list)

    def __inst_counts(self, instance_list):
        """Display instance counts
        """
        print "Instance count: %d" % (len(instance_list),)
        state_map = {
                'running' : 0,
                'stopped' : 0,
                'terminated' : 0,
                'other' : 0,
                }
        for instance in instance_list:
            instance_state = (instance.state if instance.state in state_map
                                else 'other')
            state_map[instance_state] += 1
        for instance_state in state_map:
            print "    %12s : %4d" % (instance_state, state_map[instance_state])

    def __inst_list_cmd(self, region, selector, disp):
        """Implements the list function of the inst command
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        reservation_list = ec2_conn.get_all_instances(
                                        instance_ids=selector.resource_id_list,
                                        filters=selector.get_filter_dict())
        instance_list = []
        for reservation in reservation_list:
            instance_list.extend(reservation.instances)
        with CommandOutput(output_path=disp.get_output_file()) as pg:
            if disp.display_count:
                self.__inst_counts(instance_list)
            else:
                disp_instance_list = _preprocess(instance_list, disp)
                for instance in disp_instance_list:
                    self.__inst_display(instance, disp, pg, region)

    def __inst_terminate_cmd(self, region, instance_id_list):
        """Terminate the specified instances
        """
        if not instance_id_list:
            return
        if not confirm():
            return
        ec2_conn = self.get_ec2_conn(region)
        terminated_instance_list = ec2_conn.terminate_instances(
                                                        instance_id_list)
        req_term_set = set(instance_id_list)
        term_set = set([instance.id for instance in terminated_instance_list])
        not_term_set = req_term_set - term_set
        if not_term_set:
            print "Instances not terminated: %s" % \
                                        (", ".join(list(not_term_set)),)

    def __inst_run_cmd(self, region, ebs_optimized, instance_type,
                keypair_name, user_data, shutdown_action, arg_list):
        """Launch (run) a new instance
        """
        #
        # We only launch instances in VPC 
        # We need the following information to launch an instance:
        #       * ami-id
        #       * list of security group ids
        #       * subnet id
        #       * instance type
        #
        # Since all of these are identified by self-describing strings
        # that do not collide, we scan the argument list to extract
        # the information we need
        #
        subnet_id = None
        sg_id_list = []
        ami_id = None
        ok_to_launch = True
        if ebs_optimized is None:
            ebs_optimized = self.DEFAULT_EBS_OPTIMIZED
        if instance_type is None:
            instance_type = self.DEFAULT_INSTANCE_TYPE
        for arg in arg_list:
            if ',' in arg:
                for sg_str in arg.split(','):
                    if sg_str.startswith("sg-"):
                        sg_id_list.append(sg_str)
                    else:
                        print "Bad security group id: %s" % (sg_str,)
                        ok_to_launch = False
            elif '-' in arg:
                res_type = arg.split('-', 1)[0]
                if res_type == 'ami':
                    ami_id = arg
                elif res_type == 'subnet':
                    subnet_id = arg
                elif res_type == 'sg':
                    sg_id_list.append(arg)
            else:
                print "Unexpected argument: %s" % (arg,)
                ok_to_launch = False
        if not subnet_id:
            print "Missing subnet-id"
            ok_to_launch = False
        if not ami_id:
            print "Missing ami-id"
            ok_to_launch = False
        if not sg_id_list:
            print "Missing security group(s)"
            ok_to_launch = False
        if not ok_to_launch:
            return
        if user_data:
            user_data_base64 = base64.b64encode(user_data)
        else:
            user_data_base64 = None
        ec2_conn = self.get_ec2_conn(region)
        if not shutdown_action:
            shutdown_action = None
        reservation = ec2_conn.run_instances(ami_id,
                        instance_type=instance_type,
                        key_name=keypair_name,
                        user_data=user_data_base64,
                        subnet_id=subnet_id,
                        security_group_ids=sg_id_list,
                        instance_initiated_shutdown_behavior=shutdown_action,
                        ebs_optimized=ebs_optimized)
        instance = reservation.instances[0]
        self.cache_insert(region, [instance.id])
        print instance.id

    def __inst_start_cmd(self, region, instance_type, instance_id_list):
        """Terminate the specified instances
        """
        if not instance_id_list:
            return
        ec2_conn = self.get_ec2_conn(region)
        if instance_type is not None:
            for instance_id in instance_id_list:
                if not ec2_conn.modify_instance_attribute(instance_id,
                        "instanceType", instance_type):
                    raise CommandError(
                        "Failed to modify instance type for %s" %
                                        (instance_id,))
        started_instance_list = ec2_conn.start_instances(instance_id_list)

    def __inst_stop_cmd(self, region, instance_id_list):
        """Stop the specified instances
        """
        if not instance_id_list:
            return
        ec2_conn = self.get_ec2_conn(region)
        ec2_conn.stop_instances(instance_ids=instance_id_list)

    def __inst_reboot_cmd(self, region, instance_id_list):
        """Reboot the specified instances
        """
        if not instance_id_list:
            return
        ec2_conn = self.get_ec2_conn(region)
        ec2_conn.reboot_instances(instance_ids=instance_id_list)

    def __inst_set_attribute(self, region, args):
        """Change attributes of an instance
        """
        try:
            instance_id, attr, value = args
        except ValueError:
            print "Expecting instance-id, attribute, value"
            print "Valid attributes:"
            print "   instanceType, kernel, ramdisk, userData, disableApiTermination,"
            print "   instanceInitiatedShutdownBehavior, rootDeviceName, blockDeviceMapping,"
            print "   productCodes, sourceDestCheck, groupSet, ebsOptimized, sriovNetSupport"
            return
        ec2_conn = self.get_ec2_conn(region)
        ec2_conn.modify_instance_attribute(instance_id, attr, value)

    def __inst_cmd(self, argv):
        """Implements the inst command
        """
        cmd_terminate = False
        cmd_run_instance = False
        cmd_start_instance = False
        cmd_stop_instance = False
        cmd_reboot_instance = False
        cmd_set_attribute = False
        #cmd_instance_access = False
        ebs_optimized = None
        instance_type = None
        disp = DisplayOptions()
        selector = ResourceSelector()
        region = None
        keypair_name = None
        user_data = None
        shutdown_action = 'stop'
        opt_list, args = getopt.getopt(argv,
                                "aABc:ef:K:klO:nq:Rr:Ss:Ttu:v:XxZz:")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    selector.select_all = True
                elif opt[0] == '-A':
                        cmd_set_attribute = True
                elif opt[0] == '-B':
                    cmd_reboot_instance = True
                elif opt[0] == '-c':
                    instance_type = opt[1]
                elif opt[0] == '-e':
                    ebs_optimized = True
                elif opt[0] == '-f':
                    selector.add_filter_spec(opt[1])
                elif opt[0] == '-K':
                    keypair_name = opt[1]
                elif opt[0] == '-k':
                    disp.display_count = True
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-O':
                    disp.set_output_file(opt[1])
                elif opt[0] == '-n':
                    disp.display_name = True
                elif opt[0] == '-q':
                    selector.add_tag_filter_spec(opt[1])
                elif opt[0] == '-R':
                    cmd_run_instance = True
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-S':
                    cmd_start_instance = True
                elif opt[0] == '-s':
                    shutdown_action = opt[1]
                elif opt[0] == '-T':
                    cmd_terminate = True
                elif opt[0] == '-t':
                    disp.display_tags = True
                elif opt[0] == '-u':
                    user_data = opt[1]
                elif opt[0] == '-v':
                    selector.add_filter('vpc-id', opt[1])
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
                elif opt[0] == '-Z':
                    cmd_stop_instance = True
                elif opt[0] == '-z':
                    selector.add_filter('instance-state-name', opt[1])
        if cmd_terminate:
            self.__inst_terminate_cmd(region, args)
        elif cmd_run_instance:
            self.__inst_run_cmd(region, ebs_optimized, instance_type,
                                        keypair_name, user_data,
                                        shutdown_action, args)
        elif cmd_start_instance:
            self.__inst_start_cmd(region, instance_type, args)
        elif cmd_stop_instance:
            self.__inst_stop_cmd(region, args)
        elif cmd_reboot_instance:
            self.__inst_reboot_cmd(region, args)
        elif cmd_set_attribute:
            self.__inst_set_attribute(region, args)
        else:
            selector.set_resource_ids(args, 'i-')
            self.__inst_list_cmd(region, selector, disp)

    def do_inst(self, ln):
        """
        inst [std-options] [list-options] [-n] [-e] [-v vpc_id] [-T] [args] ...

Options:
    -A          : set instance attribute
    -B          : reboot the specified instance(s)
    -c type     : instance type (class) to launch or start; the default
                  is m1.small
    -e          : create an EBS-optimized instance (when used with -R)
    -k          : display instance counts; the instances are grouped by
                  state (running, stopped, etc.)
    -K key-name : name of keypair to pass to new instance
    -n          : display the Name tag of the instance (when used with -l)
    -R          : run (launch) a new instance
    -S          : start the specified instance(s)
    -s action   : specify the shutdown action when launching a new instance;
                  values include: 'stop', 'terminate', ''
    -T          : terminate the specified instance(s)
    -u userdata : user-data string to be passed to new instance
    -v vpc_id   : list all the instances running in the specified VPC
    -z status   : display only instances with this status
    -Z          : stop the specified instance(s)

The command arguments when -R is not specified are instance-ids.

The arguments in the case of the -R option should include the ami-id,
subnet-id and security-group-id(s); the security-group-ids can be specified
as multiple arguments or as a comma-separated list (or both). The arguments
can be specified in any order.
        """
        self.dispatch(self.__inst_cmd, ln)
