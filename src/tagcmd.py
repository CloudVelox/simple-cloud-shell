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

"""This module contains the implementation of the 'tag' command
"""

import getopt

import common

from common import CommandError
from common import CommandOutput
from common import ResourceSelector


def _expand_type(res_type):
    """Expand res_type to a resource type suitable for use as a filter
    in the tag command
    """
    EXPANSION_MAP = {   # in alphabetical order
                        'igw'  :        'internet-gateway',
                        'inst' :        'instance',
                        'nacl' :        'network-acl',
                        'rtb'  :        'route-table',
                        'sg'   :        'security-group',
                        'snap' :        'snapshot',
                        'vol'  :        'volume',
                    }
    return EXPANSION_MAP.get(res_type, res_type)


class TagCommand(common.BaseCommand):

    def __tag_list_cmd(self, region, selector):
        """Implements the list function of the tag command
        """
        if not selector.has_selection():
            return
        ec2_conn = self.get_ec2_conn(region)
        tags_list = ec2_conn.get_all_tags(filters=selector.get_filter_dict())
        with CommandOutput() as pg:
            for tag in tags_list:
                pg.prt("%-16s %-16s %-12s %s",
                            tag.res_id,
                            tag.res_type,
                            tag.name,
                            tag.value)

    @staticmethod
    def __tag_parse_args(arg_list, default_value):
        """Returns the tuple (resource_id_list, tag_dict)
        """
        #
        # We try to auto-detect the resource ids
        #
        resource_id_list = []
        tag_index = 0
        for arg in arg_list:
            if arg == '-':
                tag_index += 1
                break
            if '-' not in arg:
                break
            resource_id_list.append(arg)
            tag_index += 1
        if not resource_id_list:
            raise CommandError("No resource IDs specified")
        tag_dict = { }
        for tag_spec in arg_list[tag_index:]:
            if '=' in tag_spec:
                tag_key, tag_value = tag_spec.split('=', 1)
            else:
                tag_key, tag_value = tag_spec, default_value
            tag_dict[tag_key] = tag_value
        if not tag_dict:
            raise CommandError("No tags specified")
        return resource_id_list, tag_dict

    def __tag_delete_cmd(self, region, arg_list):
        """Implements the list function of the tag command
        """
        resource_id_list, tag_dict = self.__tag_parse_args(arg_list, None)
        ec2_conn = self.get_ec2_conn(region)
        ec2_conn.delete_tags(resource_id_list, tag_dict)

    def __tag_create_cmd(self, region, arg_list):
        """Implements the list function of the tag command
        """
        resource_id_list, tag_dict = self.__tag_parse_args(arg_list, '')
        ec2_conn = self.get_ec2_conn(region)
        ec2_conn.create_tags(resource_id_list, tag_dict)

    def __tag_cmd(self, argv):
        """Implements the tag command
        """
        cmd_create_tags = False
        cmd_delete_tags = False
        selector = ResourceSelector()
        region = None
        opt_list, args = getopt.getopt(argv, "aCDf:k:r:t:v:")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    selector.select_all = True
                elif opt[0] == '-C':
                    cmd_create_tags = True
                elif opt[0] == '-D':
                    cmd_delete_tags = True
                elif opt[0] == '-f':
                    selector.add_filter_spec(opt[1])
                elif opt[0] == '-k':
                    selector.add_filter('key', opt[1])
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-t':
                    selector.add_filter('resource-type', _expand_type(opt[1]))
                elif opt[0] == '-v':
                    selector.add_filter('value', opt[1])
        if cmd_create_tags:
            self.__tag_create_cmd(region, args)
        elif cmd_delete_tags:
            self.__tag_delete_cmd(region, args)
        else:
            self.__tag_list_cmd(region, selector)

    def do_tag(self, ln):
        """
        tag [std-options] [-f filtspec] [-k key] [-t type] [-v value] [args]

Options:
    -a          : show all tags
    -C          : create new tags (see below for the expected args)
    -D          : delete tags
    -f spec     : show tags matching the specified filter spec; the spec
                  has the form: key=value
    -t type     : show tags on resources of the specified type; available
                  types: igw, inst, nacl, rtb, sg, snap, vol
    -k key      : show tags having the specified tag key
    -v value    : show tags having the specified tag value

When creating new tags, the args have the following form:
        res-id ... res-id [-] tag-spec ... tag-spec
Example:
        tag -C i-deadbeef sg-f00fa00a - NAME=foobar
        tag -D i-deadbeef - NAME=foobar
        """
        self.dispatch(self.__tag_cmd, ln)

