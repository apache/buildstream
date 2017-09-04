import os
import pytest
import tempfile
import subprocess
import re
from contextlib import contextmanager

import http
import http.server
import socketserver
import threading

from buildstream import SourceError
from buildstream import utils

# import our common fixture
from .fixture import Setup

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'ostree',
)


class OSTreeSetup(Setup):

    def __init__(self, datafiles, tmpdir, bstfile=None):

        if not bstfile:
            bstfile = 'target.bst'

        super().__init__(datafiles, bstfile, tmpdir)


def run_ostree_bash_script():
    # Run the generate-ostree.sh script
    return subprocess.call(
        ['%s/generate-ostree.sh' % (DATA_DIR,)],
        stderr=subprocess.PIPE)


def run_ostree_cli(repo, cmd):
    if type(cmd) is not list:
        cmd = [cmd]

    arg = ['ostree', '--repo=%s' % (repo,)]
    arg.extend(cmd)
    process = subprocess.Popen(
        arg,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE)
    out, err = process.communicate()

    return process.returncode, out, err


###############################################################
#                            Tests                            #
###############################################################
def test_ostree_shell_exe():
    # Run the generate-ostree.sh script
    # Does it run ok?
    ret = run_ostree_bash_script()

    assert(ret == 0)


def test_ostree_shell_dir_exist(tmpdir):
    # tmp/repo and tmp/files directories should exist

    run_ostree_bash_script()

    assert(os.path.isdir("tmp/repo"))
    assert(os.path.isdir("tmp/files"))


def test_ostree_shell_branches():
    # only 'my/branch' should exist

    run_ostree_bash_script()
    exit, out, err = run_ostree_cli("tmp/repo", "refs")
    assert(out.decode('unicode-escape').strip() == "my/branch")

    exit, out, err = run_ostree_cli("repofoo", "refs")
    assert(err.decode('unicode-escape') != '')


def test_ostree_shell_commits():
    # only 2 commits
    global REF_HEAD, REF_NOTHEAD

    run_ostree_bash_script()
    exit, out, err = run_ostree_cli("tmp/repo", ["log", "my/branch"])

    reg = re.compile(r'commit ([a-z0-9]{64})')
    commits = [m.groups()[0] for m in reg.finditer(str(out))]
    assert(len(commits) == 2)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'head'))
def test_ostree_conf(tmpdir, datafiles):

    setup = OSTreeSetup(datafiles, tmpdir)
    assert(setup.source.get_kind() == 'ostree')

    print(setup.source.url)

    # Test other config settings
    assert(setup.source.url == 'http://127.0.0.1:8000/tmp/repo')
    assert(setup.source.tracking == 'my/branch')
    assert(setup.source.gpg_key is None)


# XXX The following test cases are broken and should be revived, checkouts
# and fetches actually work, but the scaffolding for this test case needs work.
#

# @pytest.mark.datafiles(os.path.join(DATA_DIR, 'head'))
# def test_ostree_fetch(tmpdir, datafiles):
#     setup = OSTreeSetup(datafiles, tmpdir)
#     assert(setup.source.get_kind() == 'ostree')
#
#     print("fetch cwd : {}".format(os.getcwd()))
#     # Make sure we preflight and fetch first, cant stage without fetching
#     setup.source.preflight()
#     setup.source.fetch()
#
#     # Check to see if the directory contains basic OSTree directories
#     expected = ['objects', 'config', 'tmp', 'extensions', 'state', 'refs']
#     indir = os.listdir(setup.source.mirror)
#     assert(set(expected) <= set(indir))

# @pytest.mark.datafiles(os.path.join(DATA_DIR, 'head'))
# def test_ostree_stage(tmpdir, datafiles):
#     setup = OSTreeSetup(datafiles, tmpdir)
#     assert(setup.source.get_kind() == 'ostree')

    # Make sure we preflight and fetch first, cant stage without fetching
#     setup.source.preflight()
#     setup.source.fetch()

    # Stage the file and just check that it's there
#     stagedir = os.path.join(setup.context.builddir, 'repo')
#     setup.source.stage(stagedir)
