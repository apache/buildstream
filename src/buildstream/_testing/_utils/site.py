#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#
import os
import stat
import subprocess
import sys
import tempfile
from typing import Optional  # pylint: disable=unused-import

from buildstream import utils, ProgramNotFoundError
from buildstream._platform import Platform


try:
    GIT = utils.get_host_tool("git")  # type: Optional[str]
    HAVE_GIT = True

    out = str(subprocess.check_output(["git", "--version"]), "utf-8")
    # e.g. on Git for Windows we get "git version 2.21.0.windows.1".
    # e.g. on Mac via Homebrew we get "git version 2.19.0".
    version = tuple(int(x) for x in out.split(" ")[2].split(".")[:3])
    HAVE_OLD_GIT = version < (1, 8, 5)

    GIT_ENV = {
        "GIT_AUTHOR_DATE": "1320966000 +0200",
        "GIT_AUTHOR_NAME": "tomjon",
        "GIT_AUTHOR_EMAIL": "tom@jon.com",
        "GIT_COMMITTER_DATE": "1320966000 +0200",
        "GIT_COMMITTER_NAME": "tomjon",
        "GIT_COMMITTER_EMAIL": "tom@jon.com",
    }
except ProgramNotFoundError:
    GIT = None
    HAVE_GIT = False
    HAVE_OLD_GIT = False
    GIT_ENV = {}

try:
    BZR = utils.get_host_tool("bzr")  # type: Optional[str]
    HAVE_BZR = True
    # Breezy 3.0 supports `BRZ_EMAIL` but not `BZR_EMAIL`
    BZR_ENV = {
        "BZR_EMAIL": "Testy McTesterson <testy.mctesterson@example.com>",
        "BRZ_EMAIL": "Testy McTesterson <testy.mctesterson@example.com>",
    }
except ProgramNotFoundError:
    BZR = None
    HAVE_BZR = False
    BZR_ENV = {}

try:
    utils.get_host_tool("lzip")
    HAVE_LZIP = True
except ProgramNotFoundError:
    HAVE_LZIP = False

casd_path = utils._get_host_tool_internal("buildbox-casd", search_subprojects_dir="buildbox")
CASD_SEPARATE_USER = bool(os.stat(casd_path).st_mode & stat.S_ISUID)
del casd_path

IS_LINUX = sys.platform.startswith("linux")
IS_WINDOWS = os.name == "nt"

MACHINE_ARCH = Platform.get_host_arch()

HAVE_SANDBOX = None
BUILDBOX_RUN = None

try:
    path = utils._get_host_tool_internal("buildbox-run", search_subprojects_dir="buildbox")
    subprocess.run([path, "--capabilities"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    BUILDBOX_RUN = os.path.basename(os.readlink(path))
    HAVE_SANDBOX = "buildbox-run"
except (ProgramNotFoundError, OSError, subprocess.CalledProcessError):
    pass


# Check if we have subsecond mtime support on the
# filesystem where @directory is located.
#
def have_subsecond_mtime(directory):

    try:
        test_file, test_filename = tempfile.mkstemp(dir=directory)
        os.close(test_file)
    except OSError:
        # If we can't create a temp file, lets just say this is False
        return False

    try:
        os.utime(test_filename, times=None, ns=(int(12345), int(12345)))
    except OSError:
        # If we can't set the mtime, lets just say this is False
        os.unlink(test_filename)
        return False

    try:
        stat_result = os.stat(test_filename)
    except OSError:
        # If we can't stat the file, lets just say this is False
        os.unlink(test_filename)
        return False

    os.unlink(test_filename)

    return stat_result.st_mtime_ns == 12345
