
# simple-cloud-shell (clsh)

A utility that provides shell-like access to the Amazon Web Services cloud

# Description

The clsh commands are based on the AWS resource types
(instance, VPC, subnet, volume, snapshot, etc).
Argument completion is available for resource ids.

Examples:

        inst -lan       : shows all instances
        vol -lan        : shows all volumes
        vol -l -z available -o time : shows all volumes in the 'available'
                          state, ordered by time of creation
        snap -kas       : shows number of snapshots and aggregate snapshot size
        vol -kas        : shows number of volumes and aggregate volume size,
                          number of volumes and size by volume state
                          (in-use, available), and number of volumes by
                          instance


# Installation

## Requirements

Clsh is written in Python 2.x. It has been tested with Python 2.7 and
it should work with Python 2.6.

It requires the boto library (version 2).  You can get boto from
[here](https://pypi.python.org/pypi/boto)

## Deployment

By default, clsh installs in /usr/local/bin; you need to be root to
perform the following steps:

```
cd src
make install
```

# Running

Clsh requires AWS credentials to perform AWS operations. You need
to create in your home directory a file named .awscred containing
the following lines (replace ... with the corresponding keys):

```
AWSAccessKeyId=...
AWSSecretKey=...
```

One can specify a different file containing AWS credentials, either via
the AWS_CREDENTIAL_FILE environment variable, or via the -I command line
option.

You can run clsh by:

```
$ clsh
clsh --> help

Documented commands (type help <topic>):
========================================
EOF  ari      cred  elb   help  key      nacl  region  snap    user  zone
aki  cert     dhcp  eni   igw   keypair  quit  rtb     subnet  vol 
ami  console  eip   exit  inst  mfa      rds   sg      tag     vpc 

Undocumented commands:
======================
debug

You can also try 'help options' for information on common
command options

clsh --> 
```

Several commands are named after AWS resource types:

```
        inst    : instances
        vol     : EBS volumes
        snap    : snapshots
        rtb     : route-tables
        sg      : security groups
        ...
```

The easiest way to explore the capabilities of the program is to invoke
the available commands using the reporting options:

```
        -a      : all resources
        -l      : long output
        -x      : extended output
```

Auto-completion of resource-ids is available once a particular resource
has been accessed. Here is an example:

```
clsh --> vol -la
<... output with volume information ... >
clsh --> vol -x vol-34<TAB>
```

If the volume list shown as a result of the 'vol -la' command included a
volume with the id vol-34fd123e, the following 'vol -x' command would
auto-complete the volume id once enough letters were specified to
guarantee uniqueness.

