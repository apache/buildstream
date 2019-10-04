#
#  Copyright (C) 2019 Bloomberg Finance LP
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

from ..sandbox import SandboxDummy

from .platform import Platform


class Win32(Platform):

    def maximize_open_file_limit(self):
        # Note that on Windows, we don't have the 'resource' module to help us
        # configure open file limits.
        #
        # 'psutil' provides an rlimit implementation that is only available on
        # Linux, as of version 5.3.
        #
        # Given that this limit is only important for SafeHardLinks FUSE, and
        # we don't have FUSE on Windows, this won't be an obstacle for now.
        #
        # If it does turn out to be an obstacle, beware that the Windows API
        # `_setmaxstdio` for increasing the open file limit only applies to the
        # 'stream I/O level', i.e. `fopen()` and friends. CPython opens files
        # using `_wopen()`, which is at the 'low I/O level'.
        #
        # You can see this in the function `os_open_impl` in `posixmodule.c` in
        # CPython version 3.9.
        #
        # For more information:
        # https://docs.microsoft.com/en-us/cpp/c-runtime-library/reference/setmaxstdio
        #
        pass

    @staticmethod
    def _check_dummy_sandbox_config(config):
        return True

    @staticmethod
    def _create_dummy_sandbox(*args, **kwargs):
        kwargs['dummy_reason'] = "There are no supported sandbox technologies for Win32 at this time."
        return SandboxDummy(*args, **kwargs)

    def _setup_dummy_sandbox(self):
        self.check_sandbox_config = Win32._check_dummy_sandbox_config
        self.create_sandbox = Win32._create_dummy_sandbox
        return True

    def does_support_signals(self):
        # Windows does not have good support for signals, and we shouldn't
        # handle them in the same way we do on UNIX.
        #
        # From the MSDN docs:
        #
        # > SIGINT is not supported for any Win32 application. When a CTRL+C
        # > interrupt occurs, Win32 operating systems generate a new thread to
        # > specifically handle that interrupt. This can cause a single-thread
        # > application, such as one in UNIX, to become multithreaded and cause
        # > unexpected behavior.
        #
        # > The SIGILL and SIGTERM signals are not generated under Windows.
        # > They are included for ANSI compatibility. Therefore, you can set
        # > signal handlers for these signals by using signal, and you can also
        # > explicitly generate these signals by calling raise.
        #
        # The only other signals that are defined in signal.h on Windows are
        # not relevant to us:
        #
        # - SIGABRT
        # - SIGFPE
        # - SIGSEGV
        #
        # https://docs.microsoft.com/en-gb/cpp/c-runtime-library/reference/signal
        #
        return False
