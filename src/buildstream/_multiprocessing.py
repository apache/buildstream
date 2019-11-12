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
#

# TLDR:
# ALWAYS use `.AsyncioSafeProcess` when you have an asyncio event loop running and need a `multiprocessing.Process`
#
#
# The upstream asyncio library doesn't play well with forking subprocesses while an event loop is running.
#
# The main problem that affects us is that the parent and the child will share some file handlers.
# The most important one for us is the sig_handler_fd, which the loop uses to buffer signals received
# by the app so that the asyncio loop can treat them afterwards.
#
# This sharing means that when we send a signal to the child, the sighandler in the child will write
# it back to the parent sig_handler_fd, making the parent have to treat it too.
# This is a problem for example when we sigterm the process. The scheduler will send sigterms to all its children,
# which in turn will make the scheduler receive N SIGTERMs (one per child). Which in turn will send sigterms to
# the children...
#
# We therefore provide a `AsyncioSafeProcess` derived from multiprocessing.Process  that automatically
# tries to cleanup the loop and never calls `waitpid` on the child process, which breaks our child watchers.
#
#
# Relevant issues:
#  - Asyncio: support fork (https://bugs.python.org/issue21998)
#  - Asyncio: support multiprocessing (support fork) (https://bugs.python.org/issue22087)
#  - Signal delivered to a subprocess triggers parent's handler (https://bugs.python.org/issue31489)
#
#

import multiprocessing
import signal
import sys
from asyncio import set_event_loop_policy


# _AsyncioSafeForkAwareProcess()
#
# Process class that doesn't call waitpid on its own.
# This prevents conflicts with the asyncio child watcher.
#
# Also automatically close any running asyncio loop before calling
# the actual run target
#
class _AsyncioSafeForkAwareProcess(multiprocessing.Process):
    # pylint: disable=attribute-defined-outside-init
    def start(self):
        self._popen = self._Popen(self)
        self._sentinel = self._popen.sentinel

    def run(self):
        signal.set_wakeup_fd(-1)
        set_event_loop_policy(None)

        super().run()


if sys.platform != "win32":
    # Set the default event loop policy to automatically close our asyncio loop in child processes
    AsyncioSafeProcess = _AsyncioSafeForkAwareProcess

else:
    # Windows doesn't support ChildWatcher that way anyways, we'll need another
    # implementation if we want it
    AsyncioSafeProcess = multiprocessing.Process
