import os

import pytest

from buildstream2._cas import CASCache
from buildstream2.storage._casbaseddirectory import CasBasedDirectory
from buildstream2.storage._filebaseddirectory import FileBasedDirectory

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "storage"
)


def setup_backend(backend_class, tmpdir):
    if backend_class == FileBasedDirectory:
        return backend_class(os.path.join(tmpdir, "vdir"))
    else:
        cas_cache = CASCache(tmpdir)
        return backend_class(cas_cache)


@pytest.mark.parametrize("backend", [
    FileBasedDirectory, CasBasedDirectory])
@pytest.mark.datafiles(DATA_DIR)
def test_import(tmpdir, datafiles, backend):
    original = os.path.join(str(datafiles), "original")

    c = setup_backend(backend, str(tmpdir))

    c.import_files(original)

    assert "bin/bash" in c.list_relative_paths()
    assert "bin/hello" in c.list_relative_paths()


@pytest.mark.parametrize("backend", [
    FileBasedDirectory, CasBasedDirectory])
@pytest.mark.datafiles(DATA_DIR)
def test_modified_file_list(tmpdir, datafiles, backend):
    original = os.path.join(str(datafiles), "original")
    overlay = os.path.join(str(datafiles), "overlay")

    c = setup_backend(backend, str(tmpdir))

    c.import_files(original)

    c.mark_unmodified()

    c.import_files(overlay)

    print("List of all paths in imported results: {}".format(c.list_relative_paths()))
    assert "bin/bash" in c.list_relative_paths()
    assert "bin/bash" in c.list_modified_paths()
    assert "bin/hello" not in c.list_modified_paths()
