from contextlib import contextmanager
import os

import pytest

from buildstream._cas import CASCache
from buildstream.storage._casbaseddirectory import CasBasedDirectory
from buildstream.storage._filebaseddirectory import FileBasedDirectory

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "storage")


@contextmanager
def setup_backend(backend_class, tmpdir):
    if backend_class == FileBasedDirectory:
        yield backend_class(os.path.join(tmpdir, "vdir"))
    else:
        cas_cache = CASCache(tmpdir)
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
