# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#
import os
import multiprocessing
import subprocess
import sys
import platform
from typing import Optional   # pylint: disable=unused-import

from buildstream import _site, utils, ProgramNotFoundError
from buildstream._platform import Platform


try:
    GIT = utils.get_host_tool('git')    # type: Optional[str]
    HAVE_GIT = True

    out = str(subprocess.check_output(['git', '--version']), "utf-8")
    version = tuple(int(x) for x in out.split(' ')[2].split('.'))
    HAVE_OLD_GIT = version < (1, 8, 5)

    GIT_ENV = {
        'GIT_AUTHOR_DATE': '1320966000 +0200',
        'GIT_AUTHOR_NAME': 'tomjon',
        'GIT_AUTHOR_EMAIL': 'tom@jon.com',
        'GIT_COMMITTER_DATE': '1320966000 +0200',
        'GIT_COMMITTER_NAME': 'tomjon',
        'GIT_COMMITTER_EMAIL': 'tom@jon.com'
    }
except ProgramNotFoundError:
    GIT = None
    HAVE_GIT = False
    HAVE_OLD_GIT = False
    GIT_ENV = dict()

try:
    BZR = utils.get_host_tool('bzr')    # type: Optional[str]
    HAVE_BZR = True
    BZR_ENV = {
        "BZR_EMAIL": "Testy McTesterson <testy.mctesterson@example.com>"
    }
except ProgramNotFoundError:
    BZR = None
    HAVE_BZR = False
    BZR_ENV = {}

try:
    utils.get_host_tool('bwrap')
    HAVE_BWRAP = True
    HAVE_BWRAP_JSON_STATUS = _site.get_bwrap_version() >= (0, 3, 2)
except ProgramNotFoundError:
    HAVE_BWRAP = False
    HAVE_BWRAP_JSON_STATUS = False

try:
    utils.get_host_tool('lzip')
    HAVE_LZIP = True
except ProgramNotFoundError:
    HAVE_LZIP = False

try:
    import arpy  # pylint: disable=unused-import
    HAVE_ARPY = True
except ImportError:
    HAVE_ARPY = False

try:
    utils.get_host_tool('buildbox')
    HAVE_BUILDBOX = True
except ProgramNotFoundError:
    HAVE_BUILDBOX = False

IS_LINUX = os.getenv('BST_FORCE_BACKEND', sys.platform).startswith('linux')
IS_WSL = (IS_LINUX and 'Microsoft' in platform.uname().release)
IS_WINDOWS = (os.name == 'nt')

MACHINE_ARCH = Platform.get_host_arch()

HAVE_SANDBOX = os.getenv('BST_FORCE_SANDBOX')

# TODO: document
if 'BST_FORCE_START_METHOD' in os.environ:
    start_method = os.environ['BST_FORCE_START_METHOD']
    multiprocessing.set_start_method(start_method)

if HAVE_SANDBOX is not None:
    pass
elif IS_LINUX and HAVE_BWRAP and (not IS_WSL):
    HAVE_SANDBOX = 'bwrap'
