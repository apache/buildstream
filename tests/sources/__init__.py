import os

from buildstream.plugintestutils import register_repo_kind
from tests.testutils.repo.git import Git
from tests.testutils.repo.bzr import Bzr
from tests.testutils.repo.ostree import OSTree
from tests.testutils.repo.tar import Tar
from tests.testutils.repo.zip import Zip

register_repo_kind('git', Git)
register_repo_kind('bzr', Bzr)
register_repo_kind('ostree', OSTree)
register_repo_kind('tar', Tar)
register_repo_kind('zip', Zip)


def list_dir_contents(srcdir):
    contents = set()
    for _, dirs, files in os.walk(srcdir):
        for d in dirs:
            contents.add(d)
        for f in files:
            contents.add(f)
    return contents
