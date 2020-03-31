#
#  Copyright (C) 2017 Codethink Limited
#  Copyright (C) 2018 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.

import resource

from ..sandbox import SandboxDummy

from .platform import Platform


class Darwin(Platform):

    # This value comes from OPEN_MAX in syslimits.h
    OPEN_MAX = 10240

    def maximize_open_file_limit(self):
        # Note that on Mac OSX, you may not be able to simply set the soft
        # limit to the reported hard limit, as it may not be the only limit in
        # effect. The output of these commands may be somewhat independent:
        #
        #   $ launchctl limit
        #   $ sysctl -a | grep files
        #
        # The OPEN_MAX value from syslimits.h seems to be fairly safe, although
        # users may tweak their individual systems to have different values.
        # Without a way to determine what the real limit is, we risk failing to
        # increase the limit. Perhaps the complication is why psutil does not
        # support rlimit on Mac.
        #
        old_soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        soft_limit = min(max(self.OPEN_MAX, old_soft_limit), hard_limit)
        resource.setrlimit(resource.RLIMIT_NOFILE, (soft_limit, hard_limit))

    @staticmethod
    def _check_dummy_sandbox_config(config):
        pass

    @staticmethod
    def _create_dummy_sandbox(*args, **kwargs):
        kwargs["dummy_reason"] = (
            "OSXFUSE is not supported and there are no supported sandbox " + "technologies for MacOS at this time"
        )
        return SandboxDummy(*args, **kwargs)

    def _setup_dummy_sandbox(self):
        self.check_sandbox_config = Darwin._check_dummy_sandbox_config
        self.create_sandbox = Darwin._create_dummy_sandbox
        return True
