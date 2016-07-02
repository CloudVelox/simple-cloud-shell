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

"""This modules contains the implementation of the 'mfa' command
"""

import getopt

import common

from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector


class MFACommand(common.BaseCommand):
    @staticmethod
    def __mfa_display(mfa_device, disp, pg):
        """Display mfa device information
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-14s %s", mfa_device.serial_number, mfa_device.user_name)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", mfa_device.serial_number)
            pg.prt("%15s : %-12s", "User-name", mfa_device.user_name)
        else:
            pg.prt("%s", mfa_device.serial_number)

    def __mfa_list_cmd(self, region, selector, user_name, disp):
        """Implements the mfa list functionality
        """
        if not selector.has_selection() and not user_name:
            return
        iam_conn = self.get_iam_conn(region)
        mfa_device_list = iam_conn.get_all_mfa_devices(user_name=user_name)
        with CommandOutput() as pg:
            for mfa_device in mfa_device_list:
                self.__mfa_display(mfa_device, disp, pg)

    def __mfa_cmd(self, argv):
        """Implements the mfa command
        """
        #
        # We always show all mfas; the -a option is redundant
        # but is supported for symmetry reasons.
        #
        disp = DisplayOptions()
        selector = ResourceSelector()
        region = None
        user_name = None
        opt_list, args = getopt.getopt(argv, "alr:u:x")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    selector.select_all = True
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-u':
                    user_name = opt[1]
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if False:
            # modifying command
            pass
        else:
            self.__mfa_list_cmd(region, selector, user_name, disp)

    def do_mfa(self, ln):
        """mfa
        """
        self.dispatch(self.__mfa_cmd, ln)

