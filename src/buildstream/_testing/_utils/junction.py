import subprocess
import pytest

from buildstream import _yaml
from .. import Repo
from .site import HAVE_GIT, GIT, GIT_ENV


# generate_junction()
#
# Generates a junction element with a git repository
#
# Args:
#    tmpdir: The tmpdir fixture, for storing the generated git repo
#    subproject_path: The path for the subproject, to add to the git repo
#    junction_path: The location to store the generated junction element
#    store_ref: Whether to store the ref in the junction.bst file
#
# Returns:
#    (str): The ref
#
def generate_junction(tmpdir, subproject_path, junction_path, *, store_ref=True, options=None):
    # Create a repo to hold the subproject and generate
    # a junction element for it
    #
    repo = _SimpleGit(str(tmpdir))
    source_ref = ref = repo.create(subproject_path)
    if not store_ref:
        source_ref = None

    element = {"kind": "junction", "sources": [repo.source_config(ref=source_ref)]}

    if options:
        element["config"] = {"options": options}

    _yaml.roundtrip_dump(element, junction_path)

    return ref


# A barebones Git Repo class to use for generating junctions
class _SimpleGit(Repo):
    def __init__(self, directory, subdir="repo"):
        if not HAVE_GIT:
            pytest.skip("git is not available")
        super().__init__(directory, subdir)

    def create(self, directory):
        self.copy_directory(directory, self.repo)
        self._run_git("init", ".")
        self._run_git("add", ".")
        self._run_git("commit", "-m", "Initial commit")
        return self.latest_commit()

    def latest_commit(self):
        return self._run_git("rev-parse", "HEAD", stdout=subprocess.PIPE, universal_newlines=True,).stdout.strip()

    def source_config(self, ref=None):
        return self.source_config_extra(ref)

    def source_config_extra(self, ref=None, checkout_submodules=None):
        config = {"kind": "git", "url": "file://" + self.repo, "track": "master"}
        if ref is not None:
            config["ref"] = ref
        if checkout_submodules is not None:
            config["checkout-submodules"] = checkout_submodules

        return config

    def _run_git(self, *args, **kwargs):
        argv = [GIT]
        argv.extend(args)
        if "env" not in kwargs:
            kwargs["env"] = dict(GIT_ENV, PWD=self.repo)
        kwargs.setdefault("cwd", self.repo)
        kwargs.setdefault("check", True)
        return subprocess.run(argv, **kwargs)  # pylint: disable=subprocess-run-check
