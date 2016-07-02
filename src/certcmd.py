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

"""This module contains the implementation of the 'cert' command
"""

import getopt

import common

from common import CommandError
from common import DisplayOptions
from common import CommandOutput
from common import amazon2localtime


class CertCommand(common.BaseCommand):
    @staticmethod
    def __cert_signing_display(signing_cert, disp, pg):
        """Display signing certificate information
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-14s %s", signing_cert.certificate_id,
                                        signing_cert.user_name)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s:", signing_cert.certificate_id)
            pg.prt("%15s : %-12s", "User-name", signing_cert.user_name)
            pg.prt("%15s : %s", "Status", signing_cert.status)
            pg.prt("%15s : %s", "Cert-body", signing_cert.certificate_body)
        else:
            pg.prt("%s", signing_cert.certificate_id)

    def __cert_list_signing_cmd(self, region, user_name, disp):
        """Implements the signing certificate list functionality
        """
        iam_conn = self.get_iam_conn(region)
        signing_cert_list = iam_conn.get_all_signing_certs(user_name=user_name)
        with CommandOutput() as pg:
            for signing_cert in signing_cert_list:
                self.__cert_signing_display(signing_cert, disp, pg)

    @staticmethod
    def __cert_server_display(server_cert, disp, pg):
        """Display server certificate information
        """
        if disp.display == DisplayOptions.LONG:
            pg.prt("%-14s", server_cert.server_certificate_name)
        elif disp.display == DisplayOptions.EXTENDED:
            pg.prt("%s:", server_cert.server_certificate_name)
            pg.prt("%15s : %-12s", "ARN", server_cert.arn)
            pg.prt("%15s : %s", "Cert-id", server_cert.server_certificate_id)
            pg.prt("%15s : %s", "Upload-date",
                            amazon2localtime(server_cert.upload_date))
        else:
            pg.prt("%s", server_cert.server_certificate_name)

    def __cert_list_server_cmd(self, region, path_prefix, disp):
        """Implements the server certificate list functionality
        """
        iam_conn = self.get_iam_conn(region)
        server_cert_list = iam_conn.list_server_certs(path_prefix=path_prefix)
        with CommandOutput() as pg:
            for server_cert in server_cert_list:
                self.__cert_server_display(server_cert, disp, pg)

    def __cert_upload_cmd(self, region, disp, cert_chain_file,
                                                path_prefix, arg_list):
        """Implements the server certificate upload functionality
        """
        try:
            cert_name, cert_body_file, priv_key_file = arg_list
        except ValueError:
            raise CommandError(
                "Expected arguments: cert-name cert-body private-key")
        cert_body = common.read_file_contents(cert_body_file,
                                                        "certificate body")
        priv_key = common.read_file_contents(priv_key_file, "private key")
        if cert_chain_file:
            cert_chain = common.read_file_contents(cert_chain_file,
                                                        "certificate chain")
        else:
            cert_chain = None
        if cert_body is None or priv_key is None or \
                cert_chain_file is not None and cert_chain is None:
            raise CommandError
        iam_conn = self.get_iam_conn(region)
        server_cert = iam_conn.upload_server_cert(
                                cert_name=cert_name,
                                cert_body=cert_body,
                                private_key=priv_key,
                                cert_chain=cert_chain,
                                path=path_prefix)
        self.__cert_server_display(server_cert, disp, CommandOutput())

    def __cert_delete_cmd(self, region, arg_list):
        """Delete a certificate
        """
        print "Certification deletion not yet implemented"

    def __cert_cmd(self, argv):
        """Implements the cert command
        """
        #
        # We always show all certificates; the -a option is redundant
        # but is supported for symmetry reasons.
        #
        all_certs = True
        cmd_upload = False
        cmd_delete = False
        disp = DisplayOptions()
        region = None
        path_prefix = None
        signing_cert = False    # assume server cert
        user_name = None
        cert_chain_file = None
        opt_list, args = getopt.getopt(argv, "ac:lp:r:sUu:x")
        if opt_list:
            for opt in opt_list:
                if opt[0] == '-a':
                    all_certs = True
                elif opt[0] == '-c':
                    cert_chain_file = opt[1]
                elif opt[0] == '-D':
                    cmd_delete = True
                elif opt[0] == '-l':
                    disp.display = DisplayOptions.LONG
                elif opt[0] == '-p':
                    path_prefix = opt[1]
                elif opt[0] == '-r':
                    region = opt[1]
                elif opt[0] == '-s':
                    signing_cert = True
                elif opt[0] == '-U':
                    cmd_upload = True
                elif opt[0] == '-u':
                    user_name = opt[1]
                elif opt[0] == '-x':
                    disp.display = DisplayOptions.EXTENDED
        if cmd_upload:
            if signing_cert:
                print "Ability to upload signing certs not yet implemented"
                return
            self.__cert_upload_cmd(region, disp,
                                cert_chain_file, path_prefix, args)
        elif cmd_delete:
            self.__cert_delete_cmd(region, args)
        else:
            if signing_cert:
                self.__cert_list_signing_cmd(region, path_prefix, disp)
            else:
                self.__cert_list_server_cmd(region, user_name, disp)

    def do_cert(self, ln):
        """cert [std-options] [options] [args]
Options:
    -a          : report all certificates (this is the default)
    -D          : delete a certificate
    -l          : long output
    -p path     : specify a path prefix
    -U          : upload a server certificate
    -u user     : report certificates of the specified user
    -s          : report signing certificates (as opposed to server
                  certificates); signing certificates are those used
                  in EC2 API calls
    -x          : extended output

When uploading a server certificate, the following arguments are expected:
        cert-name
        cert-body (path to a file containing the certificate)
        private-key (path to a file containing the key)
        """
        self.dispatch(self.__cert_cmd, ln)

