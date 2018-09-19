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
    [('a/b/c/textfile1', 'F', 'This is textfile 1\n')],
    [('a/b/c/textfile1', 'F', 'This is the replacement textfile 1\n')],
    [('a/b/d', 'D', '')],
    [('a/b/c', 'S', '/a/b/d')],
    [('a/b/d', 'D', ''), ('a/b/c', 'S', '/a/b/d')],
]

empty_hash_ref = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def generate_import_roots(directory):
    for fileset in range(1, len(root_filesets) + 1):
        rootname = "root{}".format(fileset)
        rootdir = os.path.join(directory, "content", rootname)

        for (path, typesymbol, content) in root_filesets[fileset - 1]:
            if typesymbol == 'F':
                (dirnames, filename) = os.path.split(path)
                os.makedirs(os.path.join(rootdir, dirnames), exist_ok=True)

                with open(os.path.join(rootdir, dirnames, filename), "wt") as f:
                    f.write(content)
            elif typesymbol == 'D':
                os.makedirs(os.path.join(rootdir, path), exist_ok=True)
            elif typesymbol == 'S':
                (dirnames, filename) = os.path.split(path)
                print("Ensuring the existence of {}".format(os.path.join(rootdir, dirnames)))
                os.makedirs(os.path.join(rootdir, dirnames), exist_ok=True)
                print("attempting to make a symlink called {} pointing to {}".format(path, content))
                os.symlink(content, os.path.join(rootdir, path))


def file_contents(path):
    with open(path, "r") as f:
        result = f.read()
    return result


def file_contents_are(path, contents):
    return file_contents(path) == contents


def create_new_vdir(root_number, fake_context, tmpdir):
    d = CasBasedDirectory(fake_context)
    d.import_files(os.path.join(tmpdir, "content", "root{}".format(root_number)))
    assert d.ref.hash != empty_hash_ref
    return d


def combinations(integer_range):
    for x in integer_range:
        for y in integer_range:
            yield (x,y)

@pytest.mark.parametrize("roots", combinations([1,2,3,4,5]))
def test_cas_import(cli, tmpdir, roots):
    print("Testing import of root {} into root {}".format(roots[0], roots[1]))
    fake_context = FakeContext()
    fake_context.artifactdir = tmpdir
    # Create some fake content
    generate_import_roots(tmpdir)

    (original, overlay) = roots

    d = create_new_vdir(original, fake_context, tmpdir)
    d2 = create_new_vdir(overlay, fake_context, tmpdir)
    d.import_files(d2)
    d.export_files(os.path.join(tmpdir, "output"))

    for item in root_filesets[overlay - 1]:
        (path, typename, content) = item
        if typename in ['F', 'S']:
            assert os.path.lexists(os.path.join(tmpdir, "output", path)), "{} did not exist in the combined virtual directory".format(path)
        if typename == 'F':
            assert file_contents_are(os.path.join(tmpdir, "output", path), content)
        elif typename == 'S':
            assert os.readlink(os.path.join(tmpdir, "output", path)) == content
        elif typename == 'D':
            # Note that isdir accepts symlinks to dirs, so a symlink to a dir is acceptable.
            assert os.path.isdir(os.path.join(tmpdir, "output", path))
