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

"""This module contains the implementation of the 'rds' command
"""

import getopt

import common

from common import DisplayOptions
from common import CommandOutput
from common import confirm
from common import amazon2localtime


class RDSCommand(common.BaseCommand):

    @staticmethod
    def __rds_inst_display(dbinstance, disp, pg):
        """Display information about the specified RDS instance.
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-20s %-10s %-10s %s",
                    dbinstance.id, dbinstance.status,
                    dbinstance.instance_class,
                    amazon2localtime(dbinstance.create_time))
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", dbinstance.id)
            pg.prt("%15s : %s", "Status", dbinstance.status)
            pg.prt("%15s : %s", "Creation-time", 
                            amazon2localtime(dbinstance.create_time))
            pg.prt("%15s : %s", "Class", dbinstance.instance_class)
            pg.prt("%15s : %s", "Engine", dbinstance.engine)
            pg.prt("%15s : %s", "Storage", dbinstance.allocated_storage)
            pg.prt("%15s : %s", "DNS-name", dbinstance.endpoint[0])
            pg.prt("%15s : %s", "Port", dbinstance.endpoint[1])
            pg.prt("%15s : %s", "MultiZone",
                                "True" if dbinstance.multi_az else "False")
            if dbinstance.availability_zone:
                pg.prt("%15s : %s", "Zone", dbinstance.availability_zone)
            pg.prt("%15s : %s", "Groups", " ".join(
                    [dbgroup.name for dbgroup in dbinstance.security_groups]))
        else:
            pg.prt("%s", dbinstance.id)

    def __rds_inst_list_cmd(self, region, dbinstance_id, disp):
        """Implements the list function of the 'rds inst' command
        """
        rds_conn = self.get_rds_conn(region)
        dbinstance_list = rds_conn.get_all_dbinstances(
                                        instance_id=dbinstance_id,)
        with CommandOutput() as pg:
            for dbinstance in dbinstance_list:
                self.__rds_inst_display(dbinstance, disp, pg)

    def __rds_inst_terminate(self, region, rds_instance_list):
        """Delete a RDS instance
        """
        if not rds_instance_list:
            return
        rds_conn = self.get_rds_conn(region)
        if not confirm():
            return
        for rds_inst_id in rds_instance_list:
            dbinst = rds_conn.delete_dbinstance(rds_inst_id,
                                                skip_final_snapshot=True)
            if dbinst:
                print "Terminated: %s" % dbinst.id
            else:
                print "Failed to terminate: %s" % rds_inst_id

    def __rds_inst_cmd(self, argv):
        """Implements the 'rds inst' command
        """
        cmd_terminate = False
        all_instances = False
        disp = DisplayOptions()
        region = None
        opt_list, args = getopt.getopt(argv, "alr:Tx")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    all_instances = True
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-T':
                    cmd_terminate = True
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if cmd_terminate:
            self.__rds_inst_terminate(region, args)
        else:
            if args:
                if len(args) != 1:
                    print "Only a single RDS instance id may be specified"
                    return
                dbinstance_id = args[0]
            else:
                dbinstance_id = None
            if all_instances or dbinstance_id:
                self.__rds_inst_list_cmd(region,
                                    None if all_instances else dbinstance_id,
                                    disp)

    @staticmethod
    def __rds_sg_display(dbsg, disp, pg):
        """Display information about the specified RDS security group.
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-20s %s", dbsg.name, dbsg.description)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", dbsg.name)
            pg.prt("%15s : %s", "Description", dbsg.description)
            if dbsg.ec2_groups:
                pg.prt("%15s : %s", "Groups-allowed",
                        ", ".join([sg.name for sg in dbsg.ec2_groups]))
            if dbsg.ip_ranges:
                pg.prt("%15s : %s", "CIDRs-allowed",
                        ", ".join([ipr.cidr_ip for ipr in dbsg.ip_ranges]))
        else:
            pg.prt("%s", dbsg.name)

    def __rds_sg_list_cmd(self, region, groupname, disp):
        """Implements the list function of the 'rds sg' command
        """
        rds_conn = self.get_rds_conn(region)
        dbsg_list = rds_conn.get_all_dbsecurity_groups(groupname=groupname)
        with CommandOutput() as pg:
            for dbsg in dbsg_list:
                self.__rds_sg_display(dbsg, disp, pg)

    def __rds_sg_delete_cmd(self, region, args):
        """Implements the delete function of the 'rds sg' command
        """
        if len(args) != 1:
            print "Expecting a single RDS security group name"
            return
        rds_conn = self.get_rds_conn(region)
        rds_conn.delete_dbsecurity_group(args[0])

    def __rds_sg_cmd(self, argv):
        """Implements the 'rds sg' command
        """
        all_sgs = False
        disp = DisplayOptions()
        region = None
        cmd_delete = False
        opt_list, args = getopt.getopt(argv, "aDlr:x")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    all_sgs = True
                elif opt[0] == '-D':
                    cmd_delete = True
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if cmd_delete:
            self.__rds_sg_delete_cmd(region, args)
        else:
            if args:
                if len(args) != 1:
                    print "Only a single RDS group name may be specified"
                    return
                groupname = args[0]
            else:
                groupname = None
            if all_sgs or groupname:
                self.__rds_sg_list_cmd(region,
                                    None if all_sgs else groupname,
                                    disp)

    @staticmethod
    def __rds_subnetg_display(subnetg, disp, pg):
        """Display information about the specified RDS subnet group.
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-20s %-12s %s", subnetg.name,
                                subnetg.status, subnetg.description)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", subnetg.name)
            pg.prt("%15s : %s", "Description", subnetg.description)
            pg.prt("%15s : %s", "Subnets", " ".join(subnetg.subnet_ids))
            pg.prt("%15s : %s", "VPC", subnetg.vpc_id)
            pg.prt("%15s : %s", "Status", subnetg.status)
        else:
            pg.prt("%s", subnetg.name)

    def __rds_subnetg_list_cmd(self, region, subnetg_name, disp):
        """Implements the list function of the 'rds subnetg' command
        """
        rds_conn = self.get_rds_conn(region)
        subnetg_list = rds_conn.get_all_db_subnet_groups(name=subnetg_name)
        with CommandOutput() as pg:
            for subnetg in subnetg_list:
                self.__rds_subnetg_display(subnetg, disp, pg)

    def __rds_subnetg_delete_cmd(self, region, args):
        """Implements the delete function of the 'rds subnetg' command
        """
        if len(args) != 1:
            print "Expecting a single RDS subnet group name"
            return
        rds_conn = self.get_rds_conn(region)
        rds_conn.delete_db_subnet_group(args[0])

    def __rds_subnetg_cmd(self, argv):
        """Implements the 'rds subnetg' command
        """
        all_subnet_groups = False
        disp = DisplayOptions()
        region = None
        cmd_delete = False
        opt_list, args = getopt.getopt(argv, "aDlr:x")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    all_subnet_groups = True
                elif opt[0] == '-D':
                    cmd_delete = True
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if cmd_delete:
            self.__rds_subnetg_delete_cmd(region, args)
        else:
            if args:
                if len(args) != 1:
                    print "Only a single RDS subnet name may be specified"
                    return
                subnetg_name = args[0]
            else:
                subnetg_name = None
            if all_subnet_groups or subnetg_name:
                self.__rds_subnetg_list_cmd(region,
                                None if all_subnet_groups else subnetg_name,
                                disp)

    def __rds_cmd(self, argv):
        """Implementation of the rds command
        """
        if not argv:
            return
        rds_type = argv[0]
        if rds_type == 'inst':
            self.__rds_inst_cmd(argv[1:])
        elif rds_type == 'sg':
            self.__rds_sg_cmd(argv[1:])
        elif rds_type == 'subnetg':
            self.__rds_subnetg_cmd(argv[1:])
        else:
            print "Unsupported RDS resource type: %s" % (rds_type,)

    def do_rds(self, ln):
        """
        rds <type> [<options>] [<args>]

        The type can be one of 'inst', 'sg', or 'subnetg'

        """
        self.dispatch(self.__rds_cmd, ln)


