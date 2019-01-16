from hashlib import sha256
import os
import pytest
import random
import tempfile
from tests.testutils import cli

from buildstream.storage._casbaseddirectory import CasBasedDirectory
from buildstream.storage._filebaseddirectory import FileBasedDirectory
from buildstream._artifactcache import ArtifactCache
from buildstream._cas import CASCache
from buildstream import utils


# These are comparitive tests that check that FileBasedDirectory and
# CasBasedDirectory act identically.

# This is a set of example file system contents. It's a set of trees
# which are either expected to be problematic or were found to be
# problematic during random testing.

# The test attempts to import each on top of each other to test
# importing works consistently.  Each tuple is defined as (<filename>,
# <type>, <content>). Type can be 'F' (file), 'S' (symlink) or 'D'
# (directory) with content being the contents for a file or the
# destination for a symlink.
root_filesets = [
    [('a/b/c/textfile1', 'F', 'This is textfile 1\n')],
    [('a/b/c/textfile1', 'F', 'This is the replacement textfile 1\n')],
    [('a/b/d', 'D', '')],
    [('a/b/c', 'S', '/a/b/d')],
    [('a/b/d', 'S', '/a/b/c')],
    [('a/b/d', 'D', ''), ('a/b/c', 'S', '/a/b/d')],
    [('a/b/c', 'D', ''), ('a/b/d', 'S', '/a/b/c')],
    [('a/b', 'F', 'This is textfile 1\n')],
    [('a/b/c', 'F', 'This is textfile 1\n')],
    [('a/b/c', 'D', '')]
]

empty_hash_ref = sha256().hexdigest()
RANDOM_SEED = 69105
NUM_RANDOM_TESTS = 10


def generate_import_roots(rootno, directory):
    rootname = "root{}".format(rootno)
    rootdir = os.path.join(directory, "content", rootname)
    if os.path.exists(rootdir):
        return
    for (path, typesymbol, content) in root_filesets[rootno - 1]:
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


def generate_random_root(rootno, directory):
    # By seeding the random number generator, we ensure these tests
    # will be repeatable, at least until Python changes the random
    # number algorithm.
    random.seed(RANDOM_SEED + rootno)
    rootname = "root{}".format(rootno)
    rootdir = os.path.join(directory, "content", rootname)
    if os.path.exists(rootdir):
        return
    things = []
    locations = ['.']
    os.makedirs(rootdir)
    for i in range(0, 100):
        location = random.choice(locations)
        thingname = "node{}".format(i)
        thing = random.choice(['dir', 'link', 'file'])
        target = os.path.join(rootdir, location, thingname)
        if thing == 'dir':
            os.makedirs(target)
            locations.append(os.path.join(location, thingname))
        elif thing == 'file':
            with open(target, "wt") as f:
                f.write("This is node {}\n".format(i))
        elif thing == 'link':
            symlink_type = random.choice(['absolute', 'relative', 'broken'])
            if symlink_type == 'broken' or not things:
                os.symlink("/broken", target)
            elif symlink_type == 'absolute':
                symlink_destination = random.choice(things)
                os.symlink(symlink_destination, target)
            else:
                symlink_destination = random.choice(things)
                relative_link = os.path.relpath(symlink_destination, start=location)
                os.symlink(relative_link, target)
        things.append(os.path.join(location, thingname))


def file_contents(path):
    with open(path, "r") as f:
        result = f.read()
    return result


def file_contents_are(path, contents):
    return file_contents(path) == contents


def create_new_casdir(root_number, cas_cache, tmpdir):
    d = CasBasedDirectory(cas_cache)
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


def _import_test(tmpdir, original, overlay, generator_function, verify_contents=False):
    cas_cache = CASCache(tmpdir)
    # Create some fake content
    generator_function(original, tmpdir)
    if original != overlay:
        generator_function(overlay, tmpdir)

    d = create_new_casdir(original, cas_cache, tmpdir)

    duplicate_cas = create_new_casdir(original, cas_cache, tmpdir)

    assert duplicate_cas.ref.hash == d.ref.hash

    d2 = create_new_casdir(overlay, cas_cache, tmpdir)
    d.import_files(d2)
    export_dir = os.path.join(tmpdir, "output-{}-{}".format(original, overlay))
    roundtrip_dir = os.path.join(tmpdir, "roundtrip-{}-{}".format(original, overlay))
    d2.export_files(roundtrip_dir)
    d.export_files(export_dir)

    if verify_contents:
        for item in root_filesets[overlay - 1]:
            (path, typename, content) = item
            realpath = resolve_symlinks(path, export_dir)
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
                # We can't do any more tests than this because it
                # depends on things present in the original. Blank
                # directories here will be ignored and the original
                # left in place.
                assert os.path.lexists(realpath)

    # Now do the same thing with filebaseddirectories and check the contents match

    files = list(utils.list_relative_paths(roundtrip_dir))
    duplicate_cas._import_files_from_directory(roundtrip_dir, files=files)
    duplicate_cas._recalculate_recursing_down()
    if duplicate_cas.parent:
        duplicate_cas.parent._recalculate_recursing_up(duplicate_cas)

    assert duplicate_cas.ref.hash == d.ref.hash


# It's possible to parameterize on both original and overlay values,
# but this leads to more tests being listed in the output than are
# comfortable.
@pytest.mark.parametrize("original", range(1, len(root_filesets) + 1))
def test_fixed_cas_import(cli, tmpdir, original):
    for overlay in range(1, len(root_filesets) + 1):
        _import_test(str(tmpdir), original, overlay, generate_import_roots, verify_contents=True)


@pytest.mark.parametrize("original", range(1, NUM_RANDOM_TESTS + 1))
def test_random_cas_import(cli, tmpdir, original):
    for overlay in range(1, NUM_RANDOM_TESTS + 1):
        _import_test(str(tmpdir), original, overlay, generate_random_root, verify_contents=False)


def _listing_test(tmpdir, root, generator_function):
    cas_cache = CASCache(tmpdir)
    # Create some fake content
    generator_function(root, tmpdir)

    d = create_new_filedir(root, tmpdir)
    filelist = list(d.list_relative_paths())

    d2 = create_new_casdir(root, cas_cache, tmpdir)
    filelist2 = list(d2.list_relative_paths())

    assert filelist == filelist2


@pytest.mark.parametrize("root", range(1, 11))
def test_random_directory_listing(cli, tmpdir, root):
    _listing_test(str(tmpdir), root, generate_random_root)


@pytest.mark.parametrize("root", [1, 2, 3, 4, 5])
def test_fixed_directory_listing(cli, tmpdir, root):
    _listing_test(str(tmpdir), root, generate_import_roots)
