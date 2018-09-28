import os
import pytest
from tests.testutils import cli

from buildstream.storage import CasBasedDirectory
from buildstream.storage import FileBasedDirectory


class FakeContext():
    def __init__(self):
        self.config_cache_quota = "65536"

    def get_projects(self):
        return []

# This is a set of example file system contents. The test attempts to import
# each on top of each other to test importing works consistently.
# Each tuple is defined as (<filename>, <type>, <content>). Type can be
# 'F' (file), 'S' (symlink) or 'D' (directory) with content being the contents
# for a file or the destination for a symlink.
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
                os.makedirs(os.path.join(rootdir, dirnames), exist_ok=True)
                os.symlink(content, os.path.join(rootdir, path))


def file_contents(path):
    with open(path, "r") as f:
        result = f.read()
    return result


def file_contents_are(path, contents):
    return file_contents(path) == contents


def create_new_casdir(root_number, fake_context, tmpdir):
    d = CasBasedDirectory(fake_context)
    d.import_files(os.path.join(tmpdir, "content", "root{}".format(root_number)))
    assert d.ref.hash != empty_hash_ref
    return d

def create_new_filedir(root_number, tmpdir):
    root = os.path.join(tmpdir, "vdir")
    os.makedirs(root)
    d = FileBasedDirectory(root)
    d.import_files(os.path.join(tmpdir, "content", "root{}".format(root_number)))
    return d


def combinations(integer_range):
    for x in integer_range:
        for y in integer_range:
            yield (x, y)


def resolve_symlinks(path, root):
    """ A function to resolve symlinks inside 'path' components apart from the last one.
        For example, resolve_symlinks('/a/b/c/d', '/a/b')
        will return '/a/b/f/d' if /a/b/c is a symlink to /a/b/f. The final component of
        'path' is not resolved, because we typically want to inspect the symlink found
        at that path, not its target.

    """
    components = path.split(os.path.sep)
    location = root
    for i in range(0, len(components) - 1):
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
    # If we got here, no symlinks were found. Add on the final component and return.
    location = os.path.join(location, components[-1])
    return location


def directory_not_empty(path):
    return os.listdir(path)


@pytest.mark.parametrize("original,overlay", combinations([1, 2, 3, 4, 5]))
def test_cas_import(cli, tmpdir, original, overlay):
    fake_context = FakeContext()
    fake_context.artifactdir = tmpdir
    # Create some fake content
    generate_import_roots(tmpdir)

    d = create_new_casdir(original, fake_context, tmpdir)
    d2 = create_new_casdir(overlay, fake_context, tmpdir)
    d.import_files(d2)
    d.export_files(os.path.join(tmpdir, "output"))

    for item in root_filesets[overlay - 1]:
        (path, typename, content) = item
        realpath = resolve_symlinks(path, os.path.join(tmpdir, "output"))
        if typename == 'F':
            if os.path.isdir(realpath) and directory_not_empty(realpath):
                # The file should not have overwritten the directory in this case.
                pass
            else:
                assert os.path.isfile(realpath), "{} did not exist in the combined virtual directory".format(path)
                assert file_contents_are(realpath, content)
        elif typename == 'S':
            if os.path.isdir(realpath) and directory_not_empty(realpath):
                # The symlink should not have overwritten the directory in this case.
                pass
            else:
                assert os.path.islink(realpath)
                assert os.readlink(realpath) == content
        elif typename == 'D':
            # Note that isdir accepts symlinks to dirs, so a symlink to a dir is acceptable.
            assert os.path.isdir(realpath)


@pytest.mark.parametrize("root", [1, 2, 3, 4, 5])
def test_directory_listing(cli, tmpdir, root):
    fake_context = FakeContext()
    fake_context.artifactdir = tmpdir
    # Create some fake content
    generate_import_roots(tmpdir)

    d = create_new_filedir(root, tmpdir)
    filelist = list(d.list_relative_paths())

    d2 = create_new_casdir(root, fake_context, tmpdir)
    filelist2 = list(d2.list_relative_paths())

    print("filelist for root {} via FileBasedDirectory:".format(root))
    print("{}".format(filelist))
    print("filelist for root {} via CasBasedDirectory:".format(root))
    print("{}".format(filelist2))
    assert(filelist==filelist2)
