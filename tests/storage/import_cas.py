import stat
import os
import pytest
from tests.testutils import cli, create_repo, ALL_REPO_KINDS, generate_junction

from buildstream.storage import CasBasedDirectory

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))


class FakeContext():
    def __init__(self):
        self.config_cache_quota = "65536"

    def get_projects(self):
        return []

root_filesets = [
    [('a/b/c/textfile1', 'This is textfile 1\n')],
    [('a/b/c/textfile1', 'This is the replacement textfile 1\n')],
]

empty_hash_ref = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def generate_import_roots(directory):
    for fileset in [1, 2]:
        rootname = "root{}".format(fileset)

        for (path, content) in root_filesets[fileset - 1]:
            (dirnames, filename) = os.path.split(path)
            os.makedirs(os.path.join(directory, "content", rootname, dirnames))

            with open(os.path.join(directory, "content", rootname, dirnames, filename), "wt") as f:
                f.write(content)


def test_cas_import(cli, tmpdir):
    fake_context = FakeContext()
    fake_context.artifactdir = tmpdir
    # Create some fake content
    generate_import_roots(tmpdir)

    d = CasBasedDirectory(fake_context)
    d.import_files(os.path.join(tmpdir, "content", "root1"))
    assert d.ref.hash != empty_hash_ref

    d2 = CasBasedDirectory(fake_context)
    d2.import_files(os.path.join(tmpdir, "content", "root2"))
    assert d2.ref.hash != empty_hash_ref
    print("D2 hash is {}".format(d2.ref.hash))
    d.import_files(d2)

    d.export_files(os.path.join(tmpdir, "output"))
    assert os.path.exists(os.path.join(tmpdir, "output", "a", "b", "c", "textfile1"))
    assert file_contents_are(os.path.join(tmpdir, "output", "a", "b", "c", "textfile1"), root_filesets[1][0][1])
