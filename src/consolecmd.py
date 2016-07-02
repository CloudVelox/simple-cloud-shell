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

"""This module contains the implementation of the 'console' command
"""

import getopt

import common

from common import CommandOutput


class ConsoleCommand(common.BaseCommand):
    def __console_cmd(self, argv):
        """Implements the console command
        """
        region = None
        output_file = None
        opt_list, _ = getopt.getopt(argv, "O:r:")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-O':
                    output_file = opt[1]
                elif opt[0] == '-r':
                    region = opt[1]
        if len(argv) != 1:
            print "Expecting a single instance-id"
            return
        instance_id = argv[0]
        ec2_conn = self.get_ec2_conn(region)
        output_obj = ec2_conn.get_console_output(instance_id)
        self.cache_insert(region, [instance_id])
        cons_output = output_obj.output
        if cons_output is None:
            print "No console output"
            return
        output_lines = cons_output.split('\n')
        with CommandOutput(output_path=output_file) as pg:
            for ln in output_lines:
                if ln:
                    pg.prt("%s", ln.rstrip())

    def do_console(self, ln):
        """console [std-options] instance-id

        Retrieve the console output of the specified instance
        """
        self.dispatch(self.__console_cmd, ln)

