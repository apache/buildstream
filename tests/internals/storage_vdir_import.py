#
#  Copyright (C) 2019 Bloomberg LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
from hashlib import sha256
import os
import random

import pytest

from buildstream.storage._casbaseddirectory import CasBasedDirectory
from buildstream.storage._filebaseddirectory import FileBasedDirectory
from buildstream._cas import CASCache
from buildstream.storage.directory import VirtualDirectoryError
from buildstream.utils import _set_file_mtime, _parse_timestamp


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
    [("a/b/c/textfile1", "F", "This is textfile 1\n")],
    [("a/b/c/textfile1", "F", "This is the replacement textfile 1\n")],
    [("a/b/f", "S", "/a/b/c")],
    [("a/b/c", "D", ""), ("a/b/f", "S", "/a/b/c")],
    [("a/b/f", "F", "This is textfile 1\n")],
]

empty_hash_ref = sha256().hexdigest()
RANDOM_SEED = 69105
NUM_RANDOM_TESTS = 4
TIMESTAMP = "2019-12-16T08:49:04.012Z"
MTIME = 1576486144.0120000


def generate_import_roots(rootno, directory):
    rootname = "root{}".format(rootno)
    rootdir = os.path.join(directory, "content", rootname)
    generate_import_root(rootdir, root_filesets[rootno - 1])


def generate_import_root(rootdir, filelist):
    if os.path.exists(rootdir):
        return
    for (path, typesymbol, content) in filelist:
        if typesymbol == "F":
            (dirnames, filename) = os.path.split(path)
            os.makedirs(os.path.join(rootdir, dirnames), exist_ok=True)
            fullpath = os.path.join(rootdir, dirnames, filename)
            with open(fullpath, "wt") as f:
                f.write(content)
            # set file mtime to arbitrary
            _set_file_mtime(fullpath, _parse_timestamp(TIMESTAMP))
        elif typesymbol == "D":
            os.makedirs(os.path.join(rootdir, path), exist_ok=True)
        elif typesymbol == "S":
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
    locations = ["."]
    os.makedirs(rootdir)
    for i in range(0, 100):
        location = random.choice(locations)
        thingname = "node{}".format(i)
        thing = random.choice(["dir", "link", "file"])
        if thing == "dir":
            thingname = "dir" + thingname
        target = os.path.join(rootdir, location, thingname)
        if thing == "dir":
            os.makedirs(target)
            locations.append(os.path.join(location, thingname))
        elif thing == "file":
            with open(target, "wt") as f:
                f.write("This is node {}\n".format(i))
            _set_file_mtime(target, _parse_timestamp(TIMESTAMP))
        elif thing == "link":
            symlink_type = random.choice(["absolute", "relative", "broken"])
            if symlink_type == "broken" or not things:
                os.symlink("/broken", target)
            elif symlink_type == "absolute":
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
    d.import_files(os.path.join(tmpdir, "content", "root{}".format(root_number)), properties=["mtime"])
    digest = d._get_digest()
    assert digest.hash != empty_hash_ref
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
            tail = os.path.sep.join(components[i + 1 :])

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
    cas_cache = CASCache(tmpdir, log_directory=os.path.join(tmpdir, "logs"))
    try:
        # Create some fake content
        generator_function(original, tmpdir)
        if original != overlay:
            generator_function(overlay, tmpdir)

        d = create_new_casdir(original, cas_cache, tmpdir)

        duplicate_cas = create_new_casdir(original, cas_cache, tmpdir)

        assert duplicate_cas._get_digest().hash == d._get_digest().hash

        d2 = create_new_casdir(overlay, cas_cache, tmpdir)
        d.import_files(d2, properties=["mtime"])
        export_dir = os.path.join(tmpdir, "output-{}-{}".format(original, overlay))
        roundtrip_dir = os.path.join(tmpdir, "roundtrip-{}-{}".format(original, overlay))
        d2.export_files(roundtrip_dir)
        d.export_files(export_dir)

        if verify_contents:
            for item in root_filesets[overlay - 1]:
                (path, typename, content) = item
                realpath = resolve_symlinks(path, export_dir)
                if typename == "F":
                    if os.path.isdir(realpath) and directory_not_empty(realpath):
                        # The file should not have overwritten the directory in this case.
                        pass
                    else:
                        assert os.path.isfile(realpath), "{} did not exist in the combined virtual directory".format(
                            path
                        )
                        assert file_contents_are(realpath, content)
                        roundtrip = os.path.join(roundtrip_dir, path)
                        assert os.path.getmtime(roundtrip) == MTIME
                        assert os.path.getmtime(realpath) == MTIME

                elif typename == "S":
                    if os.path.isdir(realpath) and directory_not_empty(realpath):
                        # The symlink should not have overwritten the directory in this case.
                        pass
                    else:
                        assert os.path.islink(realpath)
                        assert os.readlink(realpath) == content
                elif typename == "D":
                    # We can't do any more tests than this because it
                    # depends on things present in the original. Blank
                    # directories here will be ignored and the original
                    # left in place.
                    assert os.path.lexists(realpath)

        # Now do the same thing with filebaseddirectories and check the contents match

        duplicate_cas.import_files(roundtrip_dir, properties=["mtime"])

        assert duplicate_cas._get_digest().hash == d._get_digest().hash
    finally:
        cas_cache.release_resources()


@pytest.mark.parametrize("original", range(1, len(root_filesets) + 1))
@pytest.mark.parametrize("overlay", range(1, len(root_filesets) + 1))
def test_fixed_cas_import(tmpdir, original, overlay):
    _import_test(str(tmpdir), original, overlay, generate_import_roots, verify_contents=True)


@pytest.mark.parametrize("original", range(1, NUM_RANDOM_TESTS + 1))
@pytest.mark.parametrize("overlay", range(1, NUM_RANDOM_TESTS + 1))
def test_random_cas_import(tmpdir, original, overlay):
    _import_test(str(tmpdir), original, overlay, generate_random_root, verify_contents=False)


def _listing_test(tmpdir, root, generator_function):
    cas_cache = CASCache(tmpdir, log_directory=os.path.join(tmpdir, "logs"))
    try:
        # Create some fake content
        generator_function(root, tmpdir)

        d = create_new_filedir(root, tmpdir)
        filelist = list(d.list_relative_paths())

        d2 = create_new_casdir(root, cas_cache, tmpdir)
        filelist2 = list(d2.list_relative_paths())

        assert filelist == filelist2
    finally:
        cas_cache.release_resources()


@pytest.mark.parametrize("root", range(1, NUM_RANDOM_TESTS + 1))
def test_random_directory_listing(tmpdir, root):
    _listing_test(str(tmpdir), root, generate_random_root)


@pytest.mark.parametrize("root", range(1, len(root_filesets) + 1))
def test_fixed_directory_listing(tmpdir, root):
    _listing_test(str(tmpdir), root, generate_import_roots)


# Check that the vdir is decending and readable
def test_descend(tmpdir):
    cas_dir = os.path.join(str(tmpdir), "cas")
    cas_cache = CASCache(cas_dir, log_directory=os.path.join(str(tmpdir), "logs"))
    try:
        d = CasBasedDirectory(cas_cache)

        Content_to_check = "You got me"
        test_dir = os.path.join(str(tmpdir), "importfrom")
        filesys_discription = [("a", "D", ""), ("a/l", "D", ""), ("a/l/g", "F", Content_to_check)]
        generate_import_root(test_dir, filesys_discription)

        d.import_files(test_dir)
        digest = d.descend("a", "l").index["g"].get_digest()

        with open(cas_cache.objpath(digest)) as fp:
            content = fp.read()
        assert Content_to_check == content
    finally:
        cas_cache.release_resources()


# Check symlink logic for edgecases
# Make sure the correct erros are raised when trying
# to decend in to files or links to files
def test_bad_symlinks(tmpdir):
    cas_dir = os.path.join(str(tmpdir), "cas")
    cas_cache = CASCache(cas_dir, log_directory=os.path.join(str(tmpdir), "logs"))
    try:
        d = CasBasedDirectory(cas_cache)

        test_dir = os.path.join(str(tmpdir), "importfrom")
        filesys_discription = [("a", "D", ""), ("a/l", "S", "../target"), ("target", "F", "You got me")]
        generate_import_root(test_dir, filesys_discription)
        d.import_files(test_dir)
        exp_reason = "not-a-directory"

        with pytest.raises(VirtualDirectoryError) as error:
            d.descend("a", "l", follow_symlinks=True)
            assert error.reason == exp_reason

        with pytest.raises(VirtualDirectoryError) as error:
            d.descend("a", "l")
            assert error.reason == exp_reason

        with pytest.raises(VirtualDirectoryError) as error:
            d.descend("a", "f")
            assert error.reason == exp_reason
    finally:
        cas_cache.release_resources()


# Check symlink logic for edgecases
# Check decend accross relitive link
def test_relative_symlink(tmpdir):
    cas_dir = os.path.join(str(tmpdir), "cas")
    cas_cache = CASCache(cas_dir, log_directory=os.path.join(str(tmpdir), "logs"))
    try:
        d = CasBasedDirectory(cas_cache)

        Content_to_check = "You got me"
        test_dir = os.path.join(str(tmpdir), "importfrom")
        filesys_discription = [
            ("a", "D", ""),
            ("a/l", "S", "../target"),
            ("target", "D", ""),
            ("target/file", "F", Content_to_check),
        ]
        generate_import_root(test_dir, filesys_discription)
        d.import_files(test_dir)

        digest = d.descend("a", "l", follow_symlinks=True).index["file"].get_digest()
        with open(cas_cache.objpath(digest)) as fp:
            content = fp.read()
        assert Content_to_check == content
    finally:
        cas_cache.release_resources()


# Check symlink logic for edgecases
# Check deccend accross abs link
def test_abs_symlink(tmpdir):
    cas_dir = os.path.join(str(tmpdir), "cas")
    cas_cache = CASCache(cas_dir, log_directory=os.path.join(str(tmpdir), "logs"))
    try:
        d = CasBasedDirectory(cas_cache)

        Content_to_check = "two step file"
        test_dir = os.path.join(str(tmpdir), "importfrom")
        filesys_discription = [
            ("a", "D", ""),
            ("a/l", "S", "/target"),
            ("target", "D", ""),
            ("target/file", "F", Content_to_check),
        ]
        generate_import_root(test_dir, filesys_discription)
        d.import_files(test_dir)

        digest = d.descend("a", "l", follow_symlinks=True).index["file"].get_digest()

        with open(cas_cache.objpath(digest)) as fp:
            content = fp.read()
        assert Content_to_check == content
    finally:
        cas_cache.release_resources()


# Check symlink logic for edgecases
# Check symlink can not escape root
def test_bad_sym_escape(tmpdir):
    cas_dir = os.path.join(str(tmpdir), "cas")
    cas_cache = CASCache(cas_dir, log_directory=os.path.join(str(tmpdir), "logs"))
    try:
        d = CasBasedDirectory(cas_cache)

        test_dir = os.path.join(str(tmpdir), "importfrom")
        filesys_discription = [
            ("jail", "D", ""),
            ("jail/a", "D", ""),
            ("jail/a/l", "S", "../../target"),
            ("target", "D", ""),
            ("target/file", "F", "two step file"),
        ]
        generate_import_root(test_dir, filesys_discription)
        d.import_files(os.path.join(test_dir, "jail"))

        with pytest.raises(VirtualDirectoryError) as error:
            d.descend("a", "l", follow_symlinks=True)
            assert error.reason == "directory-not-found"
    finally:
        cas_cache.release_resources()
