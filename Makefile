#
# Copyright 2016 CloudVelox Inc. All Rights Reserved.
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

PROGRAM		= clsh
INSTALL_ROOT	= /usr/local

_BINDIR		= $(INSTALL_ROOT)/bin
_LIBEXEC	= $(INSTALL_ROOT)/libexec/$(PROGRAM)

_SOURCES	:= $(shell ls src/*.py)

install:
	install -d -m 755 $(_LIBEXEC)
	for f in $(_SOURCES) ; do \
		install -m 644 $$f $(_LIBEXEC) ;\
	done
	install -m 755 toolcall $(_BINDIR)/$(PROGRAM)

uninstall:
	rm -f $(_BINDIR)/$(PROGRAM)
	rm -rf  $(_LIBEXEC)

