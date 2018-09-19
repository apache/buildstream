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
            yield (x, y)


def resolve_symlinks(path, root):
    """ A function to resolve symlinks which are rooted at 'root'. For example, the symlink

        /a/b/c/d -> /c/e

        should resolve with the call resolve_symlinks('/a/b/c/d', '/a/b') to '/a/b/c/e'.

    """
    components = path.split(os.path.sep)
    location = root
    for i in range(0, len(components)):
        location = os.path.join(location, components[i])
        if os.path.islink(location):
            # Resolve the link, add on all the remaining components
            target = os.path.join(os.readlink(location))
            tail = os.path.sep.join(components[i + 1:])

            if target.startswith(os.path.sep):
                # Absolute link - relative to root
                location = os.path.join(root, target, tail)
            else:
                # Relative link - relative to symlink location
                location = os.path.join(location, target)
            return resolve_symlinks(location, root)
    return location


@pytest.mark.parametrize("original,overlay", combinations([1, 2, 3, 4, 5]))
def test_cas_import(cli, tmpdir, original, overlay):
    print("Testing import of root {} into root {}".format(overlay, original))
    fake_context = FakeContext()
    fake_context.artifactdir = tmpdir
    # Create some fake content
    generate_import_roots(tmpdir)

    d = create_new_vdir(original, fake_context, tmpdir)
    d2 = create_new_vdir(overlay, fake_context, tmpdir)
    d.import_files(d2)
    d.export_files(os.path.join(tmpdir, "output"))

    for item in root_filesets[overlay - 1]:
        (path, typename, content) = item
        realpath = resolve_symlinks(path, os.path.join(tmpdir, "output"))
        print("resolved {} to {}".format(path, realpath))
        if typename == 'F':
            assert os.path.isfile(realpath), "{} did not exist in the combined virtual directory".format(path)
            # Problem here - symlinks won't resolve because the root is incorrect.
            assert file_contents_are(realpath, content)
        elif typename == 'S':
            # Not currently verified.
            # assert os.path.islink(os.path.join(tmpdir, "output", path)),
            #                       "{} did not exist in the combined virtual directory".format(path)
            # assert os.readlink(os.path.join(tmpdir, "output", path)) == content
            pass
        elif typename == 'D':
            # Note that isdir accepts symlinks to dirs, so a symlink to a dir is acceptable.
            assert os.path.isdir(realpath)
