# This code was based on pytest-forked, commit 6098c1, found here:
# <https://github.com/pytest-dev/pytest-forked>
# Its copyright notice is included below.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import marshal

import py
import pytest
# XXX Using pytest private internals here
from _pytest import runner

from buildstream import utils

EXITSTATUS_TESTEXIT = 4


# copied from xdist remote
def serialize_report(rep):
    d = rep.__dict__.copy()
    if hasattr(rep.longrepr, 'toterminal'):
        d['longrepr'] = str(rep.longrepr)
    else:
        d['longrepr'] = rep.longrepr
    for name in d:
        if isinstance(d[name], py.path.local):  # pylint: disable=no-member
            d[name] = str(d[name])
        elif name == "result":
            d[name] = None  # for now
    return d


def forked_run_report(item):
    def runforked():
        # This process is now the main BuildStream process
        # for the duration of this test.
        utils._MAIN_PID = os.getpid()

        try:
            reports = runner.runtestprotocol(item, log=False)
        except KeyboardInterrupt:
            os._exit(EXITSTATUS_TESTEXIT)
        return marshal.dumps([serialize_report(x) for x in reports])

    ff = py.process.ForkedFunc(runforked)  # pylint: disable=no-member
    result = ff.waitfinish()
    if result.retval is not None:
        report_dumps = marshal.loads(result.retval)
        return [runner.TestReport(**x) for x in report_dumps]
    else:
        if result.exitstatus == EXITSTATUS_TESTEXIT:
            pytest.exit("forked test item %s raised Exit" % (item,))
        return [report_process_crash(item, result)]


def report_process_crash(item, result):
    try:
        from _pytest.compat import getfslineno
    except ImportError:
        # pytest<4.2
        path, lineno = item._getfslineno()
    else:
        path, lineno = getfslineno(item)
    info = ("%s:%s: running the test CRASHED with signal %d" %
            (path, lineno, result.signal))

    # We need to create a CallInfo instance that is pre-initialised to contain
    # info about an exception. We do this by using a function which does
    # 0/0. Also, the API varies between pytest versions.
    has_from_call = getattr(runner.CallInfo, "from_call", None) is not None
    if has_from_call:  # pytest >= 4.1
        call = runner.CallInfo.from_call(lambda: 0 / 0, "???")
    else:
        call = runner.CallInfo(lambda: 0 / 0, "???")
    call.excinfo = info

    rep = runner.pytest_runtest_makereport(item, call)
    if result.out:
        rep.sections.append(("captured stdout", result.out))
    if result.err:
        rep.sections.append(("captured stderr", result.err))
    return rep
