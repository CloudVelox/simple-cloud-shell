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

"""This module contains the implementation of the 'keypair' command
"""

import getopt

import common

from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector


class KeyPairCommand(common.BaseCommand):
    @staticmethod
    def __keypair_display(key_pair, disp, pg):
        """Display key pair information
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-20s %s", key_pair.name, key_pair.fingerprint)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s", key_pair.name)
            pg.prt("%15s : %-12s", "Fingerprint", key_pair.fingerprint)
            pg.prt("%15s : %s", "Material", key_pair.material)
        else:
            pg.prt("%s", key_pair.name)

    def __keypair_list_cmd(self, region, selector, disp):
        """Implements the key list functionality
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        key_pair_list = ec2_conn.get_all_key_pairs(
                                keynames=selector.resource_id_list,
                                filters=selector.get_filter_dict())
        with CommandOutput() as pg:
            for key_pair in key_pair_list:
                self.__keypair_display(key_pair, disp, pg)

    def __keypair_cmd(self, argv):
        """Implements the keypair command
        """
        #
        # We always show all key pairs; the -a option is redundant
        # but is supported for symmetry reasons.
        #
        selector = ResourceSelector()
        disp = DisplayOptions()
        region = None
        opt_list, args = getopt.getopt(argv, "af:lr:x")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    selector.select_all = True
                elif opt[0] == '-f':
                    selector.add_filter_spec(opt[1])
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
            self.__keypair_list_cmd(region, selector, disp)

    def do_keypair(self, ln):
        """
    keypair [std-options] [list-options]
        """
        self.dispatch(self.__keypair_cmd, ln)

