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

"""This module contains the implementation of the 'key' command
"""

import getopt

import common

from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector


class KeyCommand(common.BaseCommand):
    @staticmethod
    def __key_display(access_key, disp, pg):
        """Display access key information
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-14s", access_key.access_key_id)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", access_key.access_key_id)
            pg.prt("%15s : %-12s", "User-name", access_key.user_name)
            pg.prt("%15s : %s", "Status", access_key.status)
        else:
            pg.prt("%s", access_key.access_key_id)

    def __key_list_cmd(self, region, selector, user_name, disp):
        """Implements the key list functionality
        """
        if not selector.has_selection() or not user_name:
            return
        iam_conn = self.get_iam_conn(region)
        access_key_list = iam_conn.list_access_keys(user_name=user_name)
        with CommandOutput() as pg:
            for access_key in access_key_list:
                self.__key_display(access_key, disp, pg)

    def __key_cmd(self, argv):
        """Implements the key command
        """
        #
        # We always show all keys; the -a option is redundant
        # but is supported for symmetry reasons.
        #
        selector = ResourceSelector()
        disp = DisplayOptions()
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
            self.__key_list_cmd(region, selector, user_name, disp)

    def do_key(self, ln):
        """key
        """
        self.dispatch(self.__key_cmd, ln)

