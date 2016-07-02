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

"""This module contains the implementation of the 'user' command
"""

import getopt

import common

from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector
from common import optional


class UserCommand(common.BaseCommand):
    """Implements the 'user' command
    """

    @staticmethod
    def __user_display(user_info, disp, pg):
        """Display user information
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-14s %-16s %-20s",
                        user_info.user_name,
                        optional(user_info.user_id),
                        user_info.path)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", user_info.user_name)
            pg.prt("%15s : %-12s", "User-id", user_info.user_id)
            pg.prt("%15s : %s", "Path", user_info.path)
            pg.prt("%15s : %s", "ARN", user_info.arn)
        else:
            pg.prt("%s", user_info.user_name)

    def __user_list_cmd(self, region, selector, disp):
        """Implements the user list functionality
        """
        iam_conn = self.get_iam_conn(region)
        if selector.select_all:
            user_info_list = iam_conn.get_all_users()
            with CommandOutput() as pg:
                for user_info in user_info_list:
                    self.__user_display(user_info, disp, pg)
        else:
            with CommandOutput() as pg:
                for username in selector.resource_id_list:
                    user_info = iam_conn.get_user(username)
                    self.__user_display(user_info, disp, pg)

    def __user_cmd(self, argv):
        """Implements the user command
        """
        selector = ResourceSelector()
        disp = DisplayOptions()
        region = None
        opt_list, args = getopt.getopt(argv, "alr:x")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    selector.select_all = True
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if False:
            # modifying command
            pass
        else:
            selector.resource_id_list = args
            self.__user_list_cmd(region, selector, disp)

    def do_user(self, ln):
        """user [-lax] [-r region] [user1] [user2] ...
        """
        self.dispatch(self.__user_cmd, ln)
