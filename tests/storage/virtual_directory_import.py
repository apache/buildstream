import os
import pytest
import random
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
    [('a/b/d', 'D', ''), ('a/b/c', 'S', '/a/b/d')]
]

empty_hash_ref = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
RANDOM_SEED = 69105


def generate_import_roots(rootno, directory):
    rootname = "root{}".format(rootno)
    rootdir = os.path.join(directory, "content", rootname)

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
    random.seed(RANDOM_SEED+rootno)
    rootname = "root{}".format(rootno)
    rootdir = os.path.join(directory, "content", rootname)
    things = []
    locations = ['.']
    os.makedirs(rootdir)
    for i in range(0, 100):
        location = random.choice(locations)
        thingname = "node{}".format(i)
        thing = random.choice(['dir', 'link', 'file'])
        target = os.path.join(rootdir, location, thingname)
        description = thing
        if thing == 'dir':
            os.makedirs(target)
            locations.append(os.path.join(location, thingname))
        elif thing == 'file':
            with open(target, "wt") as f:
                f.write("This is node {}\n".format(i))
        elif thing == 'link':
            # TODO: Make some relative symlinks
            if random.randint(1, 3) == 1 or len(things) == 0:
                os.symlink("/broken", target)
                description = "symlink pointing to /broken"
            else:
                symlink_destination = random.choice(things)
                os.symlink(symlink_destination, target)
                description = "symlink pointing to {}".format(symlink_destination)
        things.append(os.path.join(location, thingname))
        print("Generated {}/{}, a {}".format(rootdir, things[-1], description))


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


def _import_test(tmpdir, original, overlay, generator_function, verify_contents=False):
    fake_context = FakeContext()
    fake_context.artifactdir = tmpdir
    # Create some fake content
    generator_function(original, tmpdir)
    if original != overlay:
        generator_function(overlay, tmpdir)
        
    d = create_new_casdir(original, fake_context, tmpdir)
    d2 = create_new_casdir(overlay, fake_context, tmpdir)
    print("Importing dir {} into {}".format(overlay, original))
    d.import_files(d2)
    d.export_files(os.path.join(tmpdir, "output"))
    
    if verify_contents:
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

    # Now do the same thing with filebaseddirectories and check the contents match
    d3 = create_new_casdir(original, fake_context, tmpdir)
    d4 = create_new_filedir(overlay, tmpdir)
    d3.import_files(d2)
    assert d.ref.hash == d3.ref.hash

@pytest.mark.parametrize("original,overlay", combinations(range(1,6)))
def test_fixed_cas_import(cli, tmpdir, original, overlay):
    _import_test(tmpdir, original, overlay, generate_import_roots, verify_contents=True)

@pytest.mark.parametrize("original,overlay", combinations(range(1,11)))
def test_random_cas_import(cli, tmpdir, original, overlay):
    _import_test(tmpdir, original, overlay, generate_random_root, verify_contents=False)

def _listing_test(tmpdir, root, generator_function):
    fake_context = FakeContext()
    fake_context.artifactdir = tmpdir
    # Create some fake content
    generator_function(root, tmpdir)

    d = create_new_filedir(root, tmpdir)
    filelist = list(d.list_relative_paths())

    d2 = create_new_casdir(root, fake_context, tmpdir)
    filelist2 = list(d2.list_relative_paths())

    print("filelist for root {} via FileBasedDirectory:".format(root))
    print("{}".format(filelist))
    print("filelist for root {} via CasBasedDirectory:".format(root))
    print("{}".format(filelist2))
    assert filelist == filelist2
    

@pytest.mark.parametrize("root", range(1,11))
def test_random_directory_listing(cli, tmpdir, root):
    _listing_test(tmpdir, root, generate_random_root)
    
@pytest.mark.parametrize("root", [1, 2, 3, 4, 5])
def test_fixed_directory_listing(cli, tmpdir, root):
    _listing_test(tmpdir, root, generate_import_roots)
