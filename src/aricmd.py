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

"""This module contains the implementation of the 'ari' command
"""

import getopt

import common

from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector


class ARICommand(common.BaseCommand):
    """Implementation of the 'ari' command
    """

    @staticmethod
    def __ari_display(ari, disp, pg):
        """Display AMI info
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-14s %-10s %-5s",
                    ari.id, ari.architecture, ari.virtualization_type)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s:", ari.id)
            pg.prt("%15s : %-12s", "State", ari.state)
            pg.prt("%15s : %s", "Location", ari.location)
            pg.prt("%15s : %s", "Public", ari.is_public)
            pg.prt("%15s : %s", "Owner", ari.owner_id)
            if ari.description:
                pg.prt("%15s : %s", "Description", ari.description)
            pg.prt("%15s : %s %s %s", "Hardware",
                                        ari.architecture,
                                        ari.virtualization_type,
                                        ari.hypervisor,
                                        )
            if disp.display_tags:
                common.display_tags(ari.tags, pg)
        else:
            print "%s" % (ari.id,)
            if disp.display_tags:
                common.display_tags(ari.tags)

    @staticmethod
    def __ari_filter(selector, ari_list):
        """Create a new list of AKIs from ari_list by keeping only the
        AKIs that match the filters in disp.
        """
        FILTER_MAP = {
                        'arch' : 'architecture',
                    }
        filter_dict = selector.get_filter_dict()
        if not filter_dict:
            return ari_list
        new_ari_list = []
        for ari in ari_list:
            match = True
            for filt in filter_dict:
                if filter_dict[filt] != getattr(ari, FILTER_MAP[filt]):
                    match = False
                    break
            if match:
                new_ari_list.append(ari)
        return new_ari_list

    def __ari_list_cmd(self, region, selector, disp):
        """Implements the list function of the snap command
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        ari_list = ec2_conn.get_all_ramdisks(
                                        ramdisk_ids=selector.resource_id_list)
        self.cache_insert(region, [ari.id for ari in ari_list])
        ari_list = self.__ari_filter(selector, ari_list)
        with CommandOutput() as pg:
            for ari in ari_list:
                self.__ari_display(ari, disp, pg)

    def __ari_cmd(self, argv):
        """Implements the ari command
        """
        selector = ResourceSelector()
        disp = DisplayOptions()
        selector = ResourceSelector()
        region = None
        opt_list, args = getopt.getopt(argv, "af:lr:tx")
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
                elif opt[0] == '-t':
                    disp.display_tags = True
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if False:
            # modifying command
            pass
        else:
            selector.resource_id_list = args
            self.__ari_list_cmd(region, selector, disp)

    def do_ari(self, ln):
        """
        ari [std-options] [-a] [-f filtspec] [-l] [-t] [-x]  [ari-id] ...

Options:
    -a          : list all kernels
    -f filtspec : filter the list of kernels; filtspec has the form key=value;
                  the only valid key is 'arch'
    -l          : long output
    -t          : list tags
    -x          : extended output
        """
        self.dispatch(self.__ari_cmd, ln)

