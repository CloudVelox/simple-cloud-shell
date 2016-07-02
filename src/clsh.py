#!/usr/bin/env python

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

"""AWS shell using boto to issue AWS API calls.

This program follows the Unix command-style; command names are terse
and verbosity is avoided, as it is expected that the user of this program
will become familiar with it and will be able to memorize the commands.
"""

import cmd
import getopt
import os
import readline
import shlex
import sys
import traceback

try:
    import boto
except ImportError:
    print >> sys.stderr, "Unable to find boto"
    sys.exit(1)

import boto.ec2
import boto.ec2.elb
import boto.iam
import boto.rds
import boto.vpc

from boto.exception import EC2ResponseError, BotoServerError

try:
    from boto.iam.connection import IAMResponseError
except ImportError:
    IAMResponseError = EC2ResponseError

#
# We assume that all the command modules reside in the same directory as
# the command itself.
#
sys.path.insert(0, os.path.dirname(sys.argv[0]))

import akicmd
import amicmd
import aricmd
import certcmd
import consolecmd
import dhcpcmd
import eipcmd
import elbcmd
import enicmd
import igwcmd
import instcmd
import keycmd
import keypaircmd
import mfacmd
import naclcmd
import rdscmd
import rtbcmd
import sgcmd
import snapcmd
import subnetcmd
import tagcmd
import usercmd
import volcmd
import vpccmd

from common import CommandError
from common import DisplayOptions

_PROGRAM = "clsh"

_HISTORY_FILE = '~/.%s_history' % (_PROGRAM,)

_DEFAULT_CREDENTIAL_FILE = os.path.join(os.environ['HOME'], ".awscred")


def _usage(msg=None):
    """Display the program's usage on stderr and exit
    """
    if msg:
        print >> sys.stderr, msg
    print >> sys.stderr, """
Usage: %s [options]

Options:
    -I credfile             : file containing AWS credentials to use;
                              the file should contain the lines
                                  AWSAccessKeyId=...
                                  AWSSecretKey=...
    -r region               : specify the AWS region
    -d                      : run the program in debug mode
    -h                      : display help
""" % (_PROGRAM,)
    sys.exit(1)


def fatal(msg):
    """Display message and exit the progrem
    """
    print >> sys.stderr, msg
    sys.exit(1)


class _Params(object):
    """This class holds the program parameters
    """
    debug = False
    region = 'us-east-1'
    credentials_file = os.environ.get("AWS_CREDENTIAL_FILE",
                                        _DEFAULT_CREDENTIAL_FILE)

    @classmethod
    def parse_options(cls):
        """parse the programs options; returns a list with the remaining args
        """
        try:
            opts, args = getopt.getopt(sys.argv[1:],
                                'dhI:r:')
        except Exception:
            _usage("error parsing options")
        for opt in opts:
            if opt[0] == '-d':
                cls.debug = True
            elif opt[0] == '-h':
                _usage()
            elif opt[0] == '-I':
                cls.credentials_file = opt[1]
            elif opt[0] == '-r':
                cls.region = opt[1]
        return args


class _ConnectionHolder(object):
    """The boto design uses different connection objects for different
    types of requests. This class is a holder of such objects.
    """
    def __init__(self):
        self.ec2_connection = None
        self.vpc_connection = None
        self.rds_connection = None
        self.elb_connection = None
        self.iam_connection = None


class _AwsCredentials(object):
    """This class keeps track of AWS credentials
    """
    def __init__(self, key_id, key_val, cred_file=None, cred_name=None):
        self.aws_key_id = key_id
        self.aws_key_val = key_val
        self.credentials_file = cred_file
        self.credentials_name = cred_name

    @staticmethod
    def extract_credentials(credentials_file):
        """Given a file compatible with the AWS_CREDENTIAL_FILE format,
        returns the tuple (key_id, key_val) or None.
        """
        key_id = None
        key_val = None
        with open(credentials_file, "r") as f:
            for ln in f:
                if '=' not in ln:
                    continue
                key, val = ln.rstrip().split('=', 1)
                if key == 'AWSAccessKeyId':
                    key_id = val
                elif key == 'AWSSecretKey':
                    key_val = val
        if key_id is not None and key_val is not None:
            return _AwsCredentials(key_id, key_val, credentials_file)
        if key_id is None:
            print "File %s missing AWSAccessKeyId" % (credentials_file,)
        if key_val is None:
            print "File %s missing AWSSecretKey" % (credentials_file,)
        return None


class _ResourceCache(object):
    """An object of this class holds resource id of a particular
    resource type.
    """
    def __init__(self):
        #
        # Key: resource type (ex. 'vpc', 'vol', 'i')
        # Value: set of resource numbers
        #
        self.__contents = { }

    def lookup(self, res_type, res_num_prefix):
        """Returns a list of resource numbers matching the specified resource
        type and prefix.
        """
        if res_type not in self.__contents:
            return []
        res_set = self.__contents[res_type]
        match_list = [res_num for res_num in res_set
                                        if res_num.startswith(res_num_prefix)]
        return match_list

    def clear(self, res_type=None):
        """Clear the set of cached resource ids
        """
        if res_type:
            self.__contents.pop(res_type, None)
        else:
            self.__contents.clear()

    def insert(self, res_id_list):
        """Add the resource ids in res_id_list to the cache.
        """
        for res_id in res_id_list:
            if '-' not in res_id:
                continue
            res_type, res_num = res_id.split('-', 1)
            try:
                res_set = self.__contents[res_type]
            except KeyError:
                res_set = self.__contents[res_type] = set()
            res_set.add(res_num)

    def remove(self, res_id_list):
        """Remove the specified resource ids from the cache
        """
        for res_id in res_id_list:
            if '-' not in res_id:
                continue
            res_type, res_num = res_id.split('-', 1)
            try:
                # Note that remove() of a non-existing element from
                # a set results in a KeyError
                self.__contents[res_type].remove(res_num)
            except KeyError:
                pass


class _CommandInterpreter(cmd.Cmd):
    """The AWS shell command interpreter

    Common pattern for all commands:

    - The command with no arguments or options does nothing; one has to
      specify options and/or arguments for something to happen.
    - Options that modify AWS state (create/delete/modify resource, etc.)
      use capital letter options

    When listing resources there are 5 ways of specifying the resources
    to be listed:
        1) specify the resource-id's as arguments
                subnet -l subnet-3c952151
        2) use the -a option to specify all resource-id's
                subnet -a
        3) use the -f option to specify a subset of all resource-id's as
           selected by the specified filter
                subnet -l -f vpc-id=vpc-54942039
           The filter-spec has the form <key>=<value>; check the AWS
           documentation for valid keys
        4) use the -q option to specify a subset of all resource-id's as
           selected by the specified tag filter
                subnet -l -q =panos-rc2
           The tag-filter-spec has the form <key>[=<value>] or =<value>
        5) use a command-specific filter
                subnet -l -v vpc-54942039
           (the last form is a shorthand for the -f option)
    """

    STOP = True
    CONTINUE = False

    __EC2_CONN = 1
    __VPC_CONN = 2
    __RDS_CONN = 3
    __ELB_CONN = 4
    __IAM_CONN = 5

    IAM_REGION_NAME = "universal"

    def __init__(self, region, credentials_file, debug):
        cmd.Cmd.__init__(self)
        self.__region = region
        self.__debug = debug
        self.prompt = _PROGRAM + " --> "
        self.__command = {
                        'aki' : akicmd.AKICommand(self),
                        'ami' : amicmd.AMICommand(self),
                        'ari' : aricmd.ARICommand(self),
                        'cert' : certcmd.CertCommand(self),
                        'console' : consolecmd.ConsoleCommand(self),
                        'dhcp' : dhcpcmd.DHCPCommand(self),
                        'eip' : eipcmd.EIPCommand(self),
                        'elb' : elbcmd.ELBCommand(self),
                        'eni' : enicmd.ENICommand(self),
                        'igw' : igwcmd.IGWCommand(self),
                        'inst' : instcmd.InstCommand(self),
                        'key' : keycmd.KeyCommand(self),
                        'keypair' : keypaircmd.KeyPairCommand(self),
                        'mfa' : mfacmd.MFACommand(self),
                        'nacl' : naclcmd.NACLCommand(self),
                        'rds' : rdscmd.RDSCommand(self),
                        'rtb' : rtbcmd.RTBCommand(self),
                        'sg' : sgcmd.SGCommand(self),
                        'snap' : snapcmd.SnapCommand(self),
                        'subnet' : subnetcmd.SubnetCommand(self),
                        'tag' : tagcmd.TagCommand(self),
                        'user' : usercmd.UserCommand(self),
                        'vol' : volcmd.VolCommand(self),
                        'vpc' : vpccmd.VPCCommand(self),
                }
        #
        # Key: region-name
        # Value: _ConnectionHolder
        #
        self.__connmap = {}
        self.__have_region_names = False
        self.__creds = _AwsCredentials.extract_credentials(credentials_file)
        if self.__creds is None:
            fatal("Exiting due to lack of AWS credentials")
        #
        # Key: region-name
        # Value: zone-name-list
        #
        self.__zone_cache = { }
        self.__cache = _ResourceCache()

    def __find_regions(self):
        """Returns list of AWS region names.
        """
        if self.__have_region_names:
            return
        region_info_list = boto.ec2.regions()
        for region_info in region_info_list:
            self.__connmap[region_info.name] = _ConnectionHolder()
        self.__have_region_names = True

    def __get_conn(self, region, conn_type):
        """Returns a connection object. The region argument identifies the
        region to use. The connection to the particular region is established
        on-demand and then cached.
        The type of connection returned depends on the conn_type argument.
        """
        if region is None:
            region = self.__region
        if region not in self.__connmap:
            self.__find_regions()
            if region not in self.__connmap:
                raise CommandError("%s is not a valid region name" % (region,))
        holder = self.__connmap[region]
        if conn_type == self.__VPC_CONN:
            if holder.vpc_connection is None:
                holder.vpc_connection = boto.vpc.connect_to_region(region,
                                aws_access_key_id=self.__creds.aws_key_id,
                                aws_secret_access_key=self.__creds.aws_key_val)
            return holder.vpc_connection
        elif conn_type == self.__EC2_CONN:
            if holder.ec2_connection is None:
                holder.ec2_connection = boto.ec2.connect_to_region(region,
                                aws_access_key_id=self.__creds.aws_key_id,
                                aws_secret_access_key=self.__creds.aws_key_val)
            return holder.ec2_connection
        elif conn_type == self.__RDS_CONN:
            if holder.rds_connection is None:
                holder.rds_connection = boto.rds.connect_to_region(region,
                                aws_access_key_id=self.__creds.aws_key_id,
                                aws_secret_access_key=self.__creds.aws_key_val)
            return holder.rds_connection
        elif conn_type == self.__ELB_CONN:
            if holder.elb_connection is None:
                holder.elb_connection = boto.ec2.elb.connect_to_region(region,
                                aws_access_key_id=self.__creds.aws_key_id,
                                aws_secret_access_key=self.__creds.aws_key_val)
            return holder.elb_connection
        elif conn_type == self.__IAM_CONN:
            if holder.iam_connection is None:
                holder.iam_connection = boto.iam.connect_to_region(
                                self.IAM_REGION_NAME,
                                aws_access_key_id=self.__creds.aws_key_id,
                                aws_secret_access_key=self.__creds.aws_key_val)
            return holder.iam_connection
        else:
            raise CommandError("Bad connection type: %s" % (conn_type,))

    def get_iam_conn(self, region):
        """Returns an IAM connection object. The region argument identifies the
        region to use. The connection to the particular region is established
        on-demand and then cached.
        """
        return self.__get_conn(region, self.__IAM_CONN)

    def get_elb_conn(self, region):
        """Returns an ELB connection object. The region argument identifies the
        region to use. The connection to the particular region is established
        on-demand and then cached.
        """
        return self.__get_conn(region, self.__ELB_CONN)

    def get_rds_conn(self, region):
        """Returns an RDS connection object. The region argument identifies the
        region to use. The connection to the particular region is established
        on-demand and then cached.
        """
        return self.__get_conn(region, self.__RDS_CONN)

    def get_vpc_conn(self, region):
        """Returns an VPC connection object. The region argument identifies the
        region to use. The connection to the particular region is established
        on-demand and then cached.
        """
        return self.__get_conn(region, self.__VPC_CONN)

    def get_ec2_conn(self, region):
        """Returns an EC2 connection object. The region argument identifies the
        region to use. The connection to the particular region is established
        on-demand and then cached.
        """
        return self.__get_conn(region, self.__EC2_CONN)

    def cache_insert(self, res_id_list):
        return self.__cache.insert(res_id_list)

    def cache_remove(self, res_id_list):
        return self.__cache.remove(res_id_list)

    def __find_zones(self, region):
        ec2_conn = self.get_ec2_conn(region)
        self.__zone_cache[region] = ec2_conn.get_all_zones()

    def is_valid_zone(self, region, zone_name):
        """Returns True if zone is a valid zone name in the specified region
        """
        if region is None:
            region = self.__region
        if region not in self.__zone_cache:
            self.__find_zones(region)
        return zone_name in [zone.name for zone in self.__zone_cache[region]]

    def get_valid_zone_names(self, region):
        if region is None:
            region = self.__region
        if region not in self.__zone_cache:
            self.__find_zones(region)
        return [zone.name for zone in self.__zone_cache[region]]

    def dispatch(self, meth, ln):
        """This method breaks the remaining arguments in the input line
        into an argv list suitable for passing to getopt.
        It then dispatches to the method specified via the 'meth' argument.
        Dispatched methods may raise one of the explicitly caught exceptions
        listed here.
        """
        try:
            #
            # Note that 'meth' is a bound method (i.e. it already
            # has a 'self' argument associated with it.
            #
            meth(shlex.split(ln))
        except EC2ResponseError, ec2err:
            print "EC2 operation failed with error %s: %s" % \
                (ec2err.error_code, ec2err.error_message)
            if self.__debug:
                print traceback.format_exc()
        except IAMResponseError, iam_err:
            print "IAM operation failed with error %s: %s" % \
                (iam_err.error_code, iam_err.error_message)
            if self.__debug:
                print traceback.format_exc()
        except BotoServerError, serverr:
            print "Operation failed with error %s: %s" % \
                (serverr.error_code, serverr.error_message)
            if self.__debug:
                print traceback.format_exc()
        except CommandError as cmderr:
            print "%s" % cmderr
        except getopt.GetoptError, ge:
            print "Error parsing options: %s" % (ge,)
            if self.__debug:
                print traceback.format_exc()
        except Exception, ex:
            print "Unexpected exception: %s" % (ex,)
            print traceback.format_exc()

    def do_aki(self, ln):
        """aki command
        """
        self.__command['aki'].do_aki(ln)
        return self.CONTINUE

    def do_ami(self, ln):
        """ami command
        """
        self.__command['ami'].do_ami(ln)
        return self.CONTINUE

    def do_ari(self, ln):
        """ari command
        """
        self.__command['ari'].do_ari(ln)
        return self.CONTINUE

    def do_cert(self, ln):
        """cert command
        """
        self.__command['cert'].do_cert(ln)
        return self.CONTINUE

    def do_console(self, ln):
        """console command
        """
        self.__command['console'].do_console(ln)
        return self.CONTINUE

    def __debug_cmd(self, argv):
        """Implements the debug command
        """
        if argv:
            if len(argv) != 1:
                print "Expecting a single 'on' or 'off' argument"
                return
            arg = argv[0].lower()
            if arg == 'on':
                self.__debug = True
            elif arg == 'off':
                self.__debug = False
            else:
                print "Expecting a single 'on' or 'off' argument"
                return
        else:
            print "Debug: %s" % ('on' if self.__debug else 'off',)

    def do_debug(self, ln):
        self.dispatch(self.__debug_cmd, ln)
        return self.CONTINUE

    def do_dhcp(self, ln):
        """dhcp command
        """
        self.__command['dhcp'].do_dhcp(ln)
        return self.CONTINUE

    def __cred_list_cmd(self):
        """Implements the cred-list functionality
        """
        # XXX: it would be nice to also show the account id
        print "%-10s : %s" % ("Key ID", self.__creds.aws_key_id,)
        print "%-10s : %s" % ("Key Value", self.__creds.aws_key_val)
        if self.__creds.credentials_name:
            print "%-10s : %s" % ("Name", self.__creds.credentials_name)
        if self.__creds.credentials_file:
            print "%-10s : %s" % ("File", self.__creds.credentials_file)

    def __cred_set_from_file(self, credentials_file, cred_name):
        """Use the AWS credentials in the specified file (the file
        format is that of AWS_CREDENTIAL_FILE)
        """
        try:
            new_creds = _AwsCredentials.extract_credentials(credentials_file)
            if new_creds is None:
                return
        except IOError, ioe:
            raise CommandError("Unable to access %s: %s" %
                                        (credentials_file, ioe))
        self.__creds = new_creds
        self.__creds.credentials_file = credentials_file
        self.__creds.credentials_name = cred_name
        # Forget about all previous connections
        self.__connmap = {}
        self.__have_region_names = False
        self.__cache.clear()

    def __cred_cmd(self, argv):
        """Implements the cred command
        """
        cmd_list_cred = False
        cmd_set_cred_name = False
        cmd_set_keys_from_file = False
        cred_name = None
        opt_list, args = getopt.getopt(argv, "F:lN:")
        for opt in opt_list:
            if opt[0] == '-l':
                cmd_list_cred = True
            elif opt[0] == '-F':
                cmd_set_keys_from_file = True
                credentials_file = opt[1]
            elif opt[0] == '-N':
                cmd_set_cred_name = True
                cred_name = opt[1]
        if args:
            print "No args expected"
            return
        if cmd_list_cred:
            self.__cred_list_cmd()
        elif cmd_set_cred_name:
            self.__creds.credentials_name = cred_name
        elif cmd_set_keys_from_file:
            cred_file_path = os.path.expanduser(credentials_file)
            cred_file_path = os.path.expandvars(cred_file_path)
            self.__cred_set_from_file(cred_file_path, cred_name)
        else:
            self.__cred_list_cmd()

    def do_cred(self, ln):
        """
        cred [-l] [-F aws_credential_file] [-N name]

Options:
    -l          : list the current credentials
    -F file     : read credentials from the specified file (will be reported
                  by the -l option)
    -N name     : use the specified name to identify the credentials (will
                  be reported by the -l option)
        """
        self.dispatch(self.__cred_cmd, ln)
        return self.CONTINUE

    def do_eip(self, ln):
        """eip command
        """
        self.__command['eip'].do_eip(ln)
        return self.CONTINUE

    def do_elb(self, ln):
        """elb command
        """
        self.__command['elb'].do_elb(ln)
        return self.CONTINUE

    def do_eni(self, ln):
        """eni command
        """
        self.__command['eni'].do_eni(ln)
        return self.CONTINUE

    def do_igw(self, ln):
        """igw command
        """
        self.__command['igw'].do_igw(ln)
        return self.CONTINUE

    def do_inst(self, ln):
        """inst command
        """
        self.__command['inst'].do_inst(ln)
        return self.CONTINUE

    def do_key(self, ln):
        """key command
        """
        self.__command['key'].do_key(ln)
        return self.CONTINUE

    def do_keypair(self, ln):
        """keypair command
        """
        self.__command['keypair'].do_keypair(ln)
        return self.CONTINUE

    def do_mfa(self, ln):
        """mfa command
        """
        self.__command['mfa'].do_mfa(ln)
        return self.CONTINUE

    def do_nacl(self, ln):
        """nacl command
        """
        self.__command['nacl'].do_nacl(ln)
        return self.CONTINUE

    def __region_cmd(self, argv):
        """Implements the region command
        """
        opt_list, args = getopt.getopt(argv, "aS:")
        cmd_set_region = False
        cmd_list_all_regions = False
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    cmd_list_all_regions = True
                elif opt[0] == '-S':
                    cmd_set_region = True
                    new_region = opt[1]
        if args:
            print "No arguments expected"
            return
        if cmd_set_region:
            self.__region = new_region
            self.__cache.clear()
        elif cmd_list_all_regions:
            self.__find_regions()
            for region_name in self.__connmap:
                print region_name
        else:
            # show current region
            print self.__region

    def do_region(self, ln):
        """region [-a] [-S new_region]

Options:
    -a             : list all regions
    -S new_region  : change the default region to new_region
        """
        self.dispatch(self.__region_cmd, ln)
        return self.CONTINUE

    def do_rds(self, ln):
        """rds command
        """
        self.__command['rds'].do_rds(ln)
        return self.CONTINUE

    def do_rtb(self, ln):
        """rtb command
        """
        self.__command['rtb'].do_rtb(ln)
        return self.CONTINUE

    def do_sg(self, ln):
        """sg command
        """
        self.__command['sg'].do_sg(ln)
        return self.CONTINUE

    def do_snap(self, ln):
        """snap command
        """
        self.__command['snap'].do_snap(ln)
        return self.CONTINUE

    def do_subnet(self, ln):
        """subnet command
        """
        self.__command['subnet'].do_subnet(ln)
        return self.CONTINUE

    def do_tag(self, ln):
        """tag command
        """
        self.__command['tag'].do_tag(ln)
        return self.CONTINUE

    def do_user(self, ln):
        """user command
        """
        self.__command['user'].do_user(ln)
        return self.CONTINUE

    def do_vol(self, ln):
        """vol command
        """
        self.__command['vol'].do_vol(ln)
        return self.CONTINUE

    def do_vpc(self, ln):
        """vpc command
        """
        self.__command['vpc'].do_vpc(ln)
        return self.CONTINUE

    @staticmethod
    def __zone_display(zone, disp):
        """Display zone info
        """
        if disp.display == DisplayOptions.LONG:
            print "%-14s %-10s %-12s %s" % \
                (zone.name, zone.state,
                zone.region_name,
                "MSG" if zone.messages else "NO-MSG")
        elif disp.display == DisplayOptions.EXTENDED:
            print "%s:" % (zone.name,)
            print "%15s : %s" % ("State", zone.state)
            print "%15s : %s" % ("Region", zone.region_name)
            for msg in zone.messages:
                print "%15s : %s" % ("Message", msg)
        else:
            print zone.name

    def __zone_list_cmd(self, region, zone_name_list, disp):
        """Implements the list function of the zone command
        """
        ec2_conn = self.get_ec2_conn(region)
        zone_list = ec2_conn.get_all_zones(zones=zone_name_list)
        #
        # Update the zone cache, but only if we got a full-list
        #
        if not zone_name_list:
            self.__zone_cache[region] = zone_list
        for zone in zone_list:
            self.__zone_display(zone, disp)

    def __zone_cmd(self, argv):
        """Implements the zone command
        """
        all_zones = False
        disp = DisplayOptions()
        region = None
        opt_list, args = getopt.getopt(argv, "alr:x")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    all_zones = True
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if all_zones or args:
            self.__zone_list_cmd(region, None if all_zones else args, disp)

    def do_zone(self, ln):
        """
        zone [-a] [-r region] [-l] [-x] [zone-name] ...
        """
        self.dispatch(self.__zone_cmd, ln)
        return self.CONTINUE

    def do_quit(self, ln):
        """quit
        Exits the CLI
        """
        _ = ln        # quiesce pylint
        return self.STOP

    def do_help(self, ln):
        """Provide help information
        """
        argv = shlex.split(ln)
        if argv:
            if argv[0] in self.__command:
                self.__command[argv[0]].do_help(argv)
                return self.CONTINUE
            if argv[0] == 'options':
                print """
The std-options are:
    -r region   : explicitly specify a region

The list-options are:

    -a          : all resources
    -f spec     : resources matching the specified filter spec; the spec
                  has the form: key=value
    -l          : long listing
    -O file     : send output to file (in addition to stdout)
    -q tag_spec : resources matching the specified tag_spec; the tag_spec
                  has the form key[=value] or =value
    -t          : list tags
    -x          : extended listing
"""
                return self.CONTINUE
        cmd.Cmd.do_help(self, ln)
        print "You can also try 'help options' for information on common"
        print "command options"
        print


    def do_exit(self, ln):
        """exit
        Exits the CLI
        """
        _ = ln        # quiesce pylint
        return self.STOP

    def do_EOF(self, ln):
        """Invoked when the user types ^D
        """
        _ = self      # quiesce pylint
        _ = ln        # quiesce pylint
        return self.STOP

    def default(self, ln):
        """Invoked when nothing else matches
        """
        print "Unknown command: %s" % (ln,)
        return self.CONTINUE

    def emptyline(self):
        """Invoked we read an empty line
        """
        return self.CONTINUE

    def completedefault(self, text, line, begidx, endidx):
        # don't attempt to match resource ids if a different region
        # was specified
        if line.find("-r") >= 0:
            return []
        #
        # The text we are given will be empty when the input is
        #       vol -x vol-<TAB>
        # But the text will also be empty in the case of
        #       vol -x <TAB>
        # So, we need to distinguish these two cases by looking at what
        # was before the text.
        #
        if begidx == 0:         # shouldn't happen
            return []
        if line[begidx-1] != '-':
            # the user must specify the resource type
            return []
        # scan backwards for the resource type
        idx = begidx - 2
        while True:
            if idx < 0:
                return []
            if line[idx] == ' ':
                break
            idx -= 1
        res_type = line[idx+1:begidx-1]
        if not res_type:
            return []
        match_res_list = self.__cache.lookup(res_type, text)
        return match_res_list


def main():
    """Once upon a time...
    """
    try:
        args = _Params.parse_options()
    except Exception, ex:
        print ex
        sys.exit(1)
    if len(args) > 0:
        _usage()

    if not os.path.exists(_Params.credentials_file):
        print >> sys.stderr, "Credentials file does not exist: %s" % (
                                        _Params.credentials_file,)
        sys.exit(1)
    interpreter = _CommandInterpreter(_Params.region, _Params.credentials_file,
                                        _Params.debug)

    history_file = os.path.expanduser(_HISTORY_FILE)
    if os.path.exists(history_file):
        readline.read_history_file(history_file)
    else:
        with open(history_file, 'w') as _:
            pass
    v = interpreter.cmdloop()
    readline.write_history_file(history_file)
    return v

if __name__ == '__main__':
    main()
