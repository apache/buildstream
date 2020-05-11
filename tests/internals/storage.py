from contextlib import contextmanager
import os
import pprint
import shutil
import stat
import glob
import hashlib
from pathlib import Path
from typing import List, Optional

import pytest

from buildstream._cas import CASCache
from buildstream.storage._casbaseddirectory import CasBasedDirectory
from buildstream.storage._filebaseddirectory import FileBasedDirectory
from buildstream.storage.directory import _FileType, VirtualDirectoryError

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


@pytest.mark.parametrize("backend", [FileBasedDirectory, CasBasedDirectory])
@pytest.mark.datafiles(DATA_DIR)
def test_modified_file_list(tmpdir, datafiles, backend):
    original = os.path.join(str(datafiles), "original")
    overlay = os.path.join(str(datafiles), "overlay")

    with setup_backend(backend, str(tmpdir)) as c:
        c.import_files(original)

        c.mark_unmodified()

        c.import_files(overlay)

        print("List of all paths in imported results: {}".format(c.list_relative_paths()))
        assert "bin/bash" in c.list_relative_paths()
        assert "bin/bash" in c.list_modified_paths()
        assert "bin/hello" not in c.list_modified_paths()


@pytest.mark.parametrize(
    "directories", [("merge-base", "merge-base"), ("empty", "empty"),],
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
        a.import_files(before, properties=properties)
        b.import_files(after, properties=properties)
        c.import_files(buildtree, properties=properties)
        copy.import_files(buildtree, properties=properties)

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
            ret = {k: v for k, v in vars(entry).items() if k != "buildstream_object"}
            if entry.type == _FileType.REGULAR_FILE:
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
                if not str(parent) in (e.name for e in combined if e.type == _FileType.DIRECTORY):
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

        st = c.stat("root-file")
        assert stat.S_ISREG(st.st_mode)

        assert c.exists("link")
        assert c.islink("link")
        assert not c.isfile("link")
        assert c.readlink("link") == "root-file"

        st = c.stat("link")
        assert stat.S_ISLNK(st.st_mode)

        assert c.exists("subdirectory")
        assert c.isdir("subdirectory")
        assert not c.isfile("subdirectory")
        subdir = c.descend("subdirectory")
        assert set(subdir) == {"subdir-file"}

        st = c.stat("subdirectory")
        assert stat.S_ISDIR(st.st_mode)


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

        with pytest.raises((OSError, VirtualDirectoryError)):
            c.remove("subdirectory")

        with pytest.raises(FileNotFoundError):
            c.remove("subdirectory", "does-not-exist")

        # Check that `remove()` doesn't follow symlinks
        c.remove("link")
        assert not c.exists("link")
        assert c.exists("root-file")

        c.remove("subdirectory", recursive=True)
        assert not c.exists("subdirectory")

        # Removing an empty directory does not require recursive=True
        c.descend("empty-directory", create=True)
        c.remove("empty-directory")


@pytest.mark.parametrize("backend", [FileBasedDirectory, CasBasedDirectory])
@pytest.mark.datafiles(DATA_DIR)
def test_rename(tmpdir, datafiles, backend):
    with setup_backend(backend, str(tmpdir)) as c:
        c.import_files(os.path.join(str(datafiles), "original"))

        c.rename(["bin", "hello"], ["bin", "hello2"])
        c.rename(["bin"], ["bin2"])

        assert c.isfile("bin2", "hello2")


# This is purely for error output; lists relative paths and
# their digests so differences are human-grokkable
def list_relative_paths(directory):
    def entry_output(entry):
        if entry.type == _FileType.DIRECTORY:
            return list_relative_paths(entry.get_directory(directory))
        elif entry.type == _FileType.SYMLINK:
            return "-> " + entry.target
        else:
            return entry.get_digest().hash

    return {name: entry_output(entry) for name, entry in directory.index.items()}


def list_paths_with_properties(directory, prefix=""):
    for leaf in directory.index.keys():
        entry = directory.index[leaf].clone()
        if directory.filename:
            entry.name = directory.filename + os.path.sep + entry.name
        yield entry
        if entry.type == _FileType.DIRECTORY:
            subdir = entry.get_directory(directory)
            yield from list_paths_with_properties(subdir)


def utime_recursively(directory, time):
    for f in glob.glob(os.path.join(directory, "**"), recursive=True):
        os.utime(f, time)


def clear_gitkeeps(directory):
    for f in glob.glob(os.path.join(directory, "**", ".gitkeep"), recursive=True):
        os.remove(f)
