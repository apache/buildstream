import os
import tarfile

from buildstream import _yaml, utils
from .. import Repo


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
    repo = _SimpleTar(str(tmpdir))
    source_ref = ref = repo.create(subproject_path)
    if not store_ref:
        source_ref = None

    element = {"kind": "junction", "sources": [repo.source_config(ref=source_ref)]}

    if options:
        element["config"] = {"options": options}

    _yaml.roundtrip_dump(element, junction_path)

    return ref


# A barebones Tar Repo class to use for generating junctions
class _SimpleTar(Repo):
    def create(self, directory):
        tarball = os.path.join(self.repo, "file.tar.gz")

        old_dir = os.getcwd()
        os.chdir(directory)
        with tarfile.open(tarball, "w:gz") as tar:
            tar.add(".")
        os.chdir(old_dir)

        return utils.sha256sum(tarball)

    def source_config(self, ref=None):
        tarball = os.path.join(self.repo, "file.tar.gz")
        config = {"kind": "tar", "url": "file://" + tarball, "directory": "", "base-dir": ""}
        if ref is not None:
            config["ref"] = ref

        return config
