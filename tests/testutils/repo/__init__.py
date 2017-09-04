import pytest
from .git import Git
from .bzr import Bzr
from .ostree import OSTree
from .tar import Tar

available_repos = {
    'git': Git,
    'bzr': Bzr,
    'ostree': OSTree,
    'tar': Tar
}


# create_repo()
#
# Convenience for creating a Repo
#
# Args:
#    kind (str): The kind of repo to create (a source plugin basename)
#    directory (str): The path where the repo will keep a cache
#
def create_repo(kind, directory):
    try:
        constructor = available_repos[kind]
    except KeyError as e:
        raise AssertionError("Unsupported repo kind {}".format(kind)) from e

    return constructor(directory)
