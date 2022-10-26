#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

from contextlib import contextmanager
import os
import pprint
import shutil
import glob
import hashlib
from pathlib import Path
from typing import List, Optional

import pytest

from buildstream import DirectoryError, FileType
from buildstream._cas import CASCache
from buildstream.storage._casbaseddirectory import CasBasedDirectory
from buildstream.storage._filebaseddirectory import FileBasedDirectory

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "storage")


@contextmanager
def setup_backend(backend_class, tmpdir):
    if backend_class == FileBasedDirectory:
        path = os.path.join(tmpdir, "vdir")
        os.mkdir(path)
        yield backend_class(path)
    else:
        cas_cache = CASCache(os.path.join(tmpdir, "cas"), log_directory=os.path.join(tmpdir, "logs"))
        try:
            yield backend_class(cas_cache)
        finally:
            cas_cache.release_resources()


@pytest.mark.parametrize("backend", [FileBasedDirectory, CasBasedDirectory])
@pytest.mark.datafiles(DATA_DIR)
def test_import(tmpdir, datafiles, backend):
    original = os.path.join(str(datafiles), "original")

    with setup_backend(backend, str(tmpdir)) as c:
        c.import_files(original)

        assert "bin/bash" in c.list_relative_paths()
        assert "bin/hello" in c.list_relative_paths()


@pytest.mark.parametrize(
    "directories",
    [
        ("merge-base", "merge-base"),
        ("empty", "empty"),
    ],
)
@pytest.mark.datafiles(DATA_DIR)
def test_merge_same_casdirs(tmpdir, datafiles, directories):
    buildtree = os.path.join(str(datafiles), "merge-buildtree")
    before = os.path.join(str(datafiles), directories[0])
    after = os.path.join(str(datafiles), directories[1])

    # Bring the directories into a canonical state
    for directory in (buildtree, before, after):
        clear_gitkeeps(directory)
        utime_recursively(directory, (100, 100))

    with setup_backend(CasBasedDirectory, str(tmpdir)) as c, setup_backend(
        CasBasedDirectory, str(tmpdir)
    ) as a, setup_backend(CasBasedDirectory, str(tmpdir)) as b:
        a.import_files(before)
        b.import_files(after)
        c.import_files(buildtree)

        assert a._get_digest() == b._get_digest(), "{}\n{}".format(
            pprint.pformat(list_relative_paths(a)), pprint.pformat(list_relative_paths(b))
        )
        old_digest = c._get_digest()
        c._apply_changes(a, b)
        # Assert that the build tree stays the same (since there were
        # no changes between a and b)
        assert c._get_digest() == old_digest


@pytest.mark.parametrize(
    "directories",
    [
        ("merge-base", "merge-replace"),
        ("merge-base", "merge-remove"),
        ("merge-base", "merge-add"),
        ("merge-base", "merge-link"),
        ("merge-base", "merge-subdirectory-replace"),
        ("merge-base", "merge-subdirectory-remove"),
        ("merge-base", "merge-subdirectory-add"),
        ("merge-base", "merge-subdirectory-link"),
        ("merge-link", "merge-link-change"),
        ("merge-subdirectory-link", "merge-link-change"),
        ("merge-base", "merge-override-with-file"),
        ("merge-base", "merge-override-with-directory"),
        ("merge-base", "merge-override-in-subdir-with-file"),
        ("merge-base", "merge-override-in-subdir-with-directory"),
        ("merge-base", "merge-override-subdirectory"),
        ("merge-override-with-new-subdirectory", "merge-subdirectory-add"),
        ("empty", "merge-subdirectory-add"),
    ],
)
@pytest.mark.datafiles(DATA_DIR)
def test_merge_casdirs(tmpdir, datafiles, directories):
    buildtree = os.path.join(str(datafiles), "merge-buildtree")
    before = os.path.join(str(datafiles), directories[0])
    after = os.path.join(str(datafiles), directories[1])

    # Bring the directories into a canonical state
    for directory in (buildtree, before, after):
        clear_gitkeeps(directory)
        utime_recursively(directory, (100, 100))

    _test_merge_dirs(before, after, buildtree, str(tmpdir))


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("modification", ["executable", "time"])
def test_merge_casdir_properties(tmpdir, datafiles, modification):
    buildtree = os.path.join(str(datafiles), "merge-buildtree")
    before = os.path.join(str(datafiles), "merge-base")
    after = os.path.join(str(tmpdir), "merge-modified")
    shutil.copytree(before, after, symlinks=True)

    # Bring the directories into a canonical state
    for directory in (buildtree, before, after):
        clear_gitkeeps(directory)
        utime_recursively(directory, (100, 100))

    if modification == "executable":
        os.chmod(os.path.join(after, "root-file"), 0o755)
    elif modification == "time":
        os.utime(os.path.join(after, "root-file"), (200, 200))

    _test_merge_dirs(before, after, buildtree, str(tmpdir), properties=["mtime"])


def _test_merge_dirs(
    before: str, after: str, buildtree: str, tmpdir: str, properties: Optional[List[str]] = None
) -> bool:
    with setup_backend(CasBasedDirectory, tmpdir) as c, setup_backend(
        CasBasedDirectory, tmpdir
    ) as copy, setup_backend(CasBasedDirectory, tmpdir) as a, setup_backend(CasBasedDirectory, tmpdir) as b:
        a._import_files_internal(before, properties=properties)
        b._import_files_internal(after, properties=properties)
        c._import_files_internal(buildtree, properties=properties)
        copy._import_files_internal(buildtree, properties=properties)

        assert c._get_digest() == copy._get_digest()

        assert a._get_digest() != b._get_digest(), "{}\n{}".format(
            pprint.pformat(list_relative_paths(a)), pprint.pformat(list_relative_paths(b))
        )
        c._apply_changes(a, b)
        # The files in c now should contain changes from b, so these
        # shouldn't be the same anymore
        assert c._get_digest() != copy._get_digest(), "{}\n{}".format(
            pprint.pformat(list_relative_paths(c)), pprint.pformat(list_relative_paths(copy))
        )

        # This is the set of paths that should have been removed
        removed = [path for path in list_paths_with_properties(a) if path not in list_paths_with_properties(b)]

        # This is the set of paths that were added in the new set
        added = [path for path in list_paths_with_properties(b) if path not in list_paths_with_properties(a)]

        # We need to strip some types of values, since they're more
        # than our little list comparisons can handle
        def make_info(entry, list_props=None):
            ret = {k: v for k, v in vars(entry).items() if k not in ("directory", "cas_cache")}
            if entry.type == FileType.REGULAR_FILE:
                # Only file digests make sense here (directory digests
                # need to be re-calculated taking into account their
                # contents).
                ret["digest"] = entry.get_digest()
            else:
                ret["digest"] = None
            return ret

        combined = [path for path in list_paths_with_properties(copy) if path not in removed]
        # Add the new list, overriding any old entries that already
        # exist.
        for path in added:
            if path.name in (o.name for o in combined):
                # Any paths that already exist must be removed
                # first
                combined = [o for o in combined if o.name != path.name]
                combined.append(path)
            else:
                combined.append(path)

        # If any paths don't have a parent directory, we need to
        # remove them now
        for e in combined:
            path = Path(e.name)
            for parent in list(path.parents)[:-1]:
                if not str(parent) in (e.name for e in combined if e.type == FileType.DIRECTORY):
                    # If not all parent directories are existing
                    # directories
                    combined = [e for e in combined if e.name != str(path)]

        assert sorted(list(make_info(e) for e in combined), key=lambda x: x["name"]) == sorted(
            list(make_info(e) for e in list_paths_with_properties(c)), key=lambda x: x["name"]
        )


@pytest.mark.parametrize("backend", [FileBasedDirectory, CasBasedDirectory])
@pytest.mark.datafiles(DATA_DIR)
def test_file_types(tmpdir, datafiles, backend):
    with setup_backend(backend, str(tmpdir)) as c:
        c.import_files(os.path.join(str(datafiles), "merge-link"))

        # Test __iter__
        assert set(c) == {"link", "root-file", "subdirectory"}

        assert c.exists("root-file")
        assert c.isfile("root-file")
        assert not c.isdir("root-file")
        assert not c.islink("root-file")

        stat = c.stat("root-file")
        assert stat.file_type == FileType.REGULAR_FILE

        assert c.exists("link")
        assert c.islink("link")
        assert not c.isfile("link")
        assert c.readlink("link") == "root-file"

        stat = c.stat("link")
        assert stat.file_type == FileType.SYMLINK

        assert c.exists("subdirectory")
        assert c.isdir("subdirectory")
        assert not c.isfile("subdirectory")
        subdir = c.open_directory("subdirectory")
        assert set(subdir) == {"subdir-file"}

        stat = c.stat("subdirectory")
        assert stat.file_type == FileType.DIRECTORY


@pytest.mark.parametrize("backend", [FileBasedDirectory, CasBasedDirectory])
@pytest.mark.datafiles(DATA_DIR)
def test_open_file(tmpdir, datafiles, backend):
    with setup_backend(backend, str(tmpdir)) as c:
        assert not c.isfile("hello")

        with c.open_file("hello", mode="w") as f:
            f.write("world")
        assert c.isfile("hello")

        assert c.file_digest("hello") == hashlib.sha256(b"world").hexdigest()

        with c.open_file("hello", mode="r") as f:
            assert f.read() == "world"


@pytest.mark.parametrize("backend", [FileBasedDirectory, CasBasedDirectory])
@pytest.mark.datafiles(DATA_DIR)
def test_remove(tmpdir, datafiles, backend):
    with setup_backend(backend, str(tmpdir)) as c:
        c.import_files(os.path.join(str(datafiles), "merge-link"))

        with pytest.raises(DirectoryError):
            c.remove("subdirectory")

        with pytest.raises(DirectoryError):
            c.remove("subdirectory/does-not-exist")

        # Check that `remove()` doesn't follow symlinks
        c.remove("link")
        assert not c.exists("link")
        assert c.exists("root-file")

        c.remove("subdirectory", recursive=True)
        assert not c.exists("subdirectory")

        # Removing an empty directory does not require recursive=True
        c.open_directory("empty-directory", create=True)
        c.remove("empty-directory")


@pytest.mark.parametrize("backend", [FileBasedDirectory, CasBasedDirectory])
@pytest.mark.datafiles(DATA_DIR)
def test_rename(tmpdir, datafiles, backend):
    with setup_backend(backend, str(tmpdir)) as c:
        c.import_files(os.path.join(str(datafiles), "original"))

        c.rename("bin/hello", "bin/hello2")
        c.rename("bin", "bin2")

        assert c.isfile("bin2/hello2")


# This is purely for error output; lists relative paths and
# their digests so differences are human-grokkable
def list_relative_paths(directory):
    def entry_output(entry):
        if entry.type == FileType.DIRECTORY:
            return list_relative_paths(entry.get_directory(directory))
        elif entry.type == FileType.SYMLINK:
            return "-> " + entry.target
        else:
            return entry.get_digest().hash

    return {name: entry_output(entry) for name, entry in directory._CasBasedDirectory__index.items()}


def list_paths_with_properties(directory, prefix=""):
    for leaf in directory._CasBasedDirectory__index.keys():
        entry = directory._CasBasedDirectory__index[leaf].clone()
        if directory._CasBasedDirectory__filename:
            entry.name = directory._CasBasedDirectory__filename + os.path.sep + entry.name
        yield entry
        if entry.type == FileType.DIRECTORY:
            subdir = entry.get_directory(directory)
            yield from list_paths_with_properties(subdir)


def utime_recursively(directory, time):
    for f in glob.glob(os.path.join(directory, "**"), recursive=True):
        os.utime(f, time)


def clear_gitkeeps(directory):
    for f in glob.glob(os.path.join(directory, "**", ".gitkeep"), recursive=True):
        os.remove(f)
