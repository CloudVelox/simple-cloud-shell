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

"""This module contains common functions and classes
"""

import calendar
import itertools
import os
import re
import subprocess
import sys
import time

class CommandError(Exception):
    """This exception is raised when a command fails
    """
    def __init__(self, msg):
        self.__msg = msg
        Exception.__init__(self)
    
    def __str__(self):
        return self.__msg or ""


def optional(s, missing="-"):
    """Maps empty/None strings to the missing parameter
    """
    return s if s else missing


def confirm(prompt=None):
    """Display the prompt, and return True/False
    """
    default_prompt = 'Are you sure'
    try:
        if prompt is None:
            prompt = default_prompt
        prompt += "? (y/n) --> "
        while True:
            v = raw_input(prompt)
            if not v:
                return False
            v = v.lower()
            if v == 'y':
                return True
            elif v == 'n':
                return False
    except EOFError:
        return False


def _make_prompt(op_name, res_list, prompt):
    """Create the prompt to display
    The res_list must not be empty.
    """
    default_prompt = 'Are you sure'
    disp_width = 60
    line_prefix = '    '
    if prompt is None:
        prompt = default_prompt
    prompt += "? (y/n) --> "
    res_width = len(str(res_list[0]))
    res_per_line = disp_width / res_width
    res_line_list = [ op_name ]
    res_list = sorted(res_list)
    for i in xrange(0, len(res_list), res_per_line):
        res_line = line_prefix + ", ".join(res_list[i:i+res_per_line])
        res_line_list.append(res_line)
    res_line_list.append(prompt)
    return '\n'.join(res_line_list)


def confirm_aggr(op_name, res_list,
                            res_name=None, show_count=False, prompt=None):
    """Confirm an operation on a group of resources
    """
    disp_prompt = _make_prompt(op_name, res_list, prompt)
    try:
        while True:
            v = raw_input(disp_prompt)
            if not v:
                return False
            v = v.lower()
            if v == 'y':
                return True
            elif v == 'n':
                return False
    except EOFError:
        return False


def amazon2unixtime(amazon_timestr):
    """Given a string in Amazon-time format (i.e. ISOFORMAT),
    return the Unix time in seconds (i.e. as returned by time(2))
    """
    try:
        tm_utc = time.strptime(amazon_timestr, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        tm_utc = None
    if tm_utc is None:
        tm_utc = time.strptime(amazon_timestr, "%Y-%m-%dT%H:%M:%SZ")
    time_sec = calendar.timegm(tm_utc)
    return time_sec


def amazon2localtime(amazon_timestr):
    """Given a string in Amazon-time format (i.e. ISOFORMAT),
    return a string for the same time moment in local time.
    """
    time_sec = amazon2unixtime(amazon_timestr)
    tm_local = time.localtime(time_sec)
    local_timestr = time.strftime("%Y-%m-%d %H:%M:%S", tm_local)
    return local_timestr


def display_tags(tag_dict, pg=None):
    """Display the tags
    """
    tag_keys = tag_dict.keys()
    tag_keys.sort()
    for tag in tag_keys:
        tag_text = "%12s = %s" % (tag, tag_dict[tag])
        if pg:
            pg.prt("%15s : %s", "TAG", tag_text)
        else:
            print "%15s : %s" % ("TAG", tag_text)


def read_file_contents(path, description):
    """Read the contents of the file at 'path' and return it as one string
    """
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception, ex:
        print "Failed to read %s from file %s: %s" % (description, path, ex)
        return None


class CommandOutput(object):
    """Process command output
    """
    def __init__(self, paginated_output=True, output_path=None):
        self.__paginated_output = paginated_output
        self.__output_path = output_path
        self.__active = False
        self.__proc = None
        self.__output_file = None

    def start(self):
        """Start the paginator
        """
        if self.__active:
            return
        self.__enter__()

    def __enter__(self):
        if self.__output_path:
            self.__output_file = open(self.__output_path, "w")
        if self.__paginated_output:
            environ = os.environ.copy()
            environ['SHELL'] = '/bin/true'
            environ['LESSSECURE'] = "1"
            environ['LESS'] = "-d -F -X -PPress 'q' to quit --> $"
            self.__proc = subprocess.Popen("/usr/bin/less",
                        shell=False,
                        close_fds=True,
                        env=environ,
                        stdin=subprocess.PIPE,
                        stdout=sys.stdout,
                        stderr=sys.stderr)
        return self

    def __exit__(self, typ, value, trcbk):
        self.finished()
        return False

    def prt(self, fmt, *args):
        """printf-like behavior
        """
        s = fmt % args
        try:
            if self.__output_file:
                self.__output_file.write(s)
                self.__output_file.write('\n')
            if self.__proc:
                print >> self.__proc.stdin, s
                self.__proc.stdin.flush()
            else:
                print s
        except IOError:
            raise CommandError

    def write(self, s):
        """Write the string s to the paginator
        """
        if self.__proc:
            self.__proc.stdin.write(s)
            self.__proc.stdin.flush()
        else:
            print s,
        if self.__output_file:
            self.__output_file.write(s)

    def wrt(self, fmt, *args):
        """Write the string s to the paginator
        """
        s = fmt % args
        self.write(s)

    def finished(self):
        """Inform the paginator that no more output is coming and wait
        for it to terminate.
        """
        if self.__proc:
            self.__proc.stdin.close()
            self.__proc.wait()
            self.__proc = None
        if self.__output_file:
            self.__output_file.close()
            self.__output_file = None
        self.__active = False


class ResourceSelector(object):
    """This class is used to identify the resources selected for
    an operation.
    """

    def __init__(self):
        self.__filter_dict = {}
        self.select_all = False
        self.resource_id_list = None
        self.match_pattern = None

    def has_selection(self):
        return self.select_all or self.resource_id_list or \
                self.__filter_dict or self.match_pattern

    def is_explicit(self):
        return bool(self.resource_id_list)

    def set_resource_ids(self, res_id_list, res_prefix=None):
        """When we want information for particular resources (say
        instances) which are specified explicitly, allow the user
        to specify either the resource id, or the value of the
        'Name' tag. Effectively, this allows one to list resources
        by name.
        """
        resource_id_list = []
        for res_id in res_id_list:
            if res_prefix and res_id.startswith(res_prefix):
                resource_id_list.append(res_id)
            else:
                self.add_tag_filter_spec('Name=' + res_id)
        self.resource_id_list = resource_id_list

    def add_filter(self, key, value):
        """Add a filter
        """
        self.__filter_dict[key] = value

    def add_tag_filter_spec(self, filter_spec):
        """Add a tag filter. The filter_spec has the form
                key=value
           where both key and value are optional (but not at
           the same time).
                filter_spec     filter-name     filter-value
                -----------     -----------     ------------
                key=value       tag:<key>       value
                key             tag-key         key
                =value          tag-value       value
        """
        if '=' in filter_spec:
            res = filter_spec.split('=', 1)
            if res[0]:
                filter_name = 'tag:' + res[0]
            else:
                filter_name = 'tag-value'
            self.__filter_dict[filter_name] = res[1]
        else:
            # NB: the current Boto EC2-related APIs expect the
            #     tags as a dictionary, which makes multiple 'tag-key'
            #     specifications impossible; the VPC-related APIs do
            #     not have this limitation, but for now our implementation,
            #     which also uses a dictionary, does not support that.
            self.__filter_dict['tag-key'] = filter_spec

    def add_filter_spec(self, filter_spec):
        """Add a filter based on filter_spec, which should have
        the form
                key=value
        A malformed filter_spec will result in an Exception.
        """
        if '=' not in filter_spec:
            raise CommandError("Bad filter spec: %s" % (filter_spec,))
        res = filter_spec.split('=', 1)
        self.__filter_dict[res[0]] = res[1]

    def get_filter_dict(self):
        """Return the filters in the form of a dictionary.
        (expected by the EC2-related APIs)
        """
        if self.__filter_dict:
            return self.__filter_dict
        else:
            return None

    def get_filter_list(self):
        """Return the filters as a list of tuples (expected by
        VPC-related APIs)
        """
        if self.__filter_dict:
            return self.__filter_dict.items()
        else:
            return None

    def filter_resources(self, resource_list):
        """Filter resources in resource_list based on the Name tag,
        and return a list containing only the resources that
        match the match_pattern in the ResourceSelector
        """
        if self.match_pattern:
            def is_name_match(resource):
                resource_name = resource.tags.get('Name')
                if resource_name is None:
                    return False
                return bool(re.search(self.match_pattern, resource_name))
            return itertools.ifilter(is_name_match, resource_list)
        else:
            return resource_list


class DisplayOptions(object):
    """This class is used to store information about what to display
    and how to display it.
    Individual commands may add additional attributes to objects
    of this class.
    """

    SIMPLE = 1            # just the resource ID
    LONG = 2              # more info, one resource-per-line
    EXTENDED = 3          # even more info, multiple lines per resource

    def __init__(self):
        self.display = self.SIMPLE
        self.display_tags = False
        self.display_name = False
        self.display_size = False
        self.display_count = False
        self.filter_dict = {}
        self.custom = None
        # __display_order_list is a list of (callable, boolean) tuples.
        # The callable is suitable to be used as the 'key' argument to
        # list.sort and the boolean sets the 'reverse' argument of list.sort;
        # this is used when displaying a list of resources to order them
        # before display.
        self.__display_order_list = []
        self.__output_file_path = None

    def add_display_order(self, order_pred, reverse):
        self.__display_order_list.append((order_pred, reverse))

    def order_resources(self, resource_list):
        """Order resources in resource_list based on 
        """
        for order_pred, reverse in self.__display_order_list:
            resource_list.sort(key=order_pred, reverse=reverse)
        return resource_list

    def set_output_file(self, file_path):
        self.__output_file_path = file_path

    def get_output_file(self):
        return self.__output_file_path


class BaseCommand(object):
    """This class serves as the base class for all commands and
    provides common methods that they can all use.
    """
    def __init__(self, interp):
        self.__interp = interp

    def get_ec2_conn(self, region):
        """Returns an EC2 connection object. The region argument identifies the
        region to use.
        """
        return self.__interp.get_ec2_conn(region)

    def get_vpc_conn(self, region):
        """Returns a VPC connection object. The region argument identifies the
        region to use.
        """
        return self.__interp.get_vpc_conn(region)

    def get_iam_conn(self, region):
        """Returns an IAM connection object. The region argument identifies the
        region to use.
        """
        return self.__interp.get_iam_conn(region)

    def get_rds_conn(self, region):
        """Returns a RDS connection object. The region argument identifies the
        region to use.
        """
        return self.__interp.get_rds_conn(region)

    def get_elb_conn(self, region):
        """Returns an ELB connection object. The region argument identifies the
        region to use.
        """
        return self.__interp.get_elb_conn(region)

    def dispatch(self, meth, ln):
        """Break ln into argv and invoke meth
        """
        return self.__interp.dispatch(meth, ln)

    def cache_insert(self, region, res_id_list):
        """Cache the resource names in res_id_list 
        """
        return self.__interp.cache_insert(res_id_list)

    def cache_remove(self, region, res_id_list):
        """Remove the resource names in res_id_list from the cache
        """
        self.__interp.cache_remove(res_id_list)

    def is_valid_zone(self, region, zone_name):
        """Returns True if zone_name is a valid zone name for the specified
        region
        """
        return self.__interp.is_valid_zone(region, zone_name)

    def get_valid_zone_names(self, region):
        """Returns a list of valid zone names for the specified region
        """
        return self.__interp.get_valid_zone_names(region)

    def do_help(self, argv):
        """Displays help information
        """
        command_name = argv[0]
        help_method_name = "help_%s" % (command_name,)
        if hasattr(self, help_method_name):
            help_method = getattr(self, help_method_name)
            if callable(help_method):
                help_method(argv)
                return
        command_method_name = "do_%s" % (command_name,)
        if hasattr(self, command_method_name):
            command_method = getattr(self, command_method_name)
            if callable(command_method):
                print getattr(command_method, "__doc__")
                return
        print "No help for command: %s" % (argv[0],)

