# Some things resolved about the execution site,
# so we dont have to repeat this everywhere
#
import os
import sys
import platform

from buildstream import _site, utils, ProgramNotFoundError


try:
    GIT = utils.get_host_tool('git')
    HAVE_GIT = True
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
    GIT_ENV = dict()

try:
    utils.get_host_tool('bwrap')
    HAVE_BWRAP = True
    HAVE_BWRAP_JSON_STATUS = _site.get_bwrap_version() >= (0, 3, 2)
except ProgramNotFoundError:
    HAVE_BWRAP = False
    HAVE_BWRAP_JSON_STATUS = False

IS_LINUX = os.getenv('BST_FORCE_BACKEND', sys.platform).startswith('linux')
IS_WSL = (IS_LINUX and 'Microsoft' in platform.uname().release)
IS_WINDOWS = (os.name == 'nt')

if not IS_LINUX:
    HAVE_SANDBOX = True   # fallback to a chroot sandbox on unix
elif IS_WSL:
    HAVE_SANDBOX = False  # Sandboxes are inoperable under WSL due to lack of FUSE
elif IS_LINUX and HAVE_BWRAP:
    HAVE_SANDBOX = True
else:
    HAVE_SANDBOX = False
