# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#
import os
import stat
import subprocess
import sys
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
    GIT_ENV = dict()

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

casd_path = utils.get_host_tool("buildbox-casd")
CASD_SEPARATE_USER = bool(os.stat(casd_path).st_mode & stat.S_ISUID)
del casd_path

IS_LINUX = sys.platform.startswith("linux")
IS_WINDOWS = os.name == "nt"

MACHINE_ARCH = Platform.get_host_arch()

HAVE_SANDBOX = None
BUILDBOX_RUN = None

try:
    path = utils.get_host_tool("buildbox-run")
    subprocess.run([path, "--capabilities"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    BUILDBOX_RUN = os.path.basename(os.readlink(path))
    HAVE_SANDBOX = "buildbox-run"
except (ProgramNotFoundError, OSError, subprocess.CalledProcessError):
    pass
