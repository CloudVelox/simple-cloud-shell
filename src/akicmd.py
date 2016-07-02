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

"""This module contains the implementation of the 'aki' command
"""

import getopt

import common

from common import DisplayOptions
from common import CommandOutput
from common import ResourceSelector


class AKICommand(common.BaseCommand):
    @staticmethod
    def __aki_display(aki, disp, pg):
        """Display AMI info
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-14s %-10s %-5s",
                    aki.id, aki.architecture, aki.virtualization_type)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s:", aki.id)
            pg.prt("%15s : %-12s", "State", aki.state)
            pg.prt("%15s : %s", "Location", aki.location)
            pg.prt("%15s : %s", "Public", aki.is_public)
            pg.prt("%15s : %s", "Owner", aki.owner_id)
            if aki.description:
                pg.prt("%15s : %s", "Description", aki.description)
            pg.prt("%15s : %s %s %s", "Hardware",
                                        aki.architecture,
                                        aki.virtualization_type,
                                        aki.hypervisor,
                                        )
            if disp.display_tags:
                common.display_tags(aki.tags, pg)
        else:
            pg.prt("%s", aki.id)
            if disp.display_tags:
                common.display_tags(aki.tags)

    @staticmethod
    def __aki_filter(selector, aki_list):
        """Create a new list of AKIs from aki_list by keeping only the
        AKIs that match the filters in disp.
        """
        FILTER_MAP = {
                        'arch' : 'architecture',
                    }
        filter_dict = selector.get_filter_dict()
        if not filter_dict:
            return aki_list
        new_aki_list = []
        for aki in aki_list:
            match = True
            for filt in filter_dict:
                if filter_dict[filt] != getattr(aki, FILTER_MAP[filt]):
                    match = False
                    break
            if match:
                new_aki_list.append(aki)
        return new_aki_list

    def __aki_list_cmd(self, region, selector, disp):
        """Implements the list function of the snap command
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        aki_list = ec2_conn.get_all_kernels(
                                        kernel_ids=selector.resource_id_list)
        self.cache_insert(region, [aki.id for aki in aki_list])
        aki_list = self.__aki_filter(selector, aki_list)
        with CommandOutput() as pg:
            for aki in aki_list:
                self.__aki_display(aki, disp, pg)

    def __aki_cmd(self, argv):
        """Implements the aki command
        """
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
            self.__aki_list_cmd(region, selector, disp)

    def do_aki(self, ln):
        """
        aki [std-options] [-a] [-f filtspec] [-l] [-t] [-x]  [aki-id] ...

Options:
    -a          : list all kernels
    -f filtspec : filter the list of kernels; filtspec has the form key=value;
                  the only valid key is 'arch'
    -l          : long output
    -t          : list tags
    -x          : extended output
        """
        self.dispatch(self.__aki_cmd, ln)

