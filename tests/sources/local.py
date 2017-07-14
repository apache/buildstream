import os
import pytest
import tempfile

from buildstream import SourceError

# import our common fixture
from .fixture import Setup

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'local',
)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_create_source(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    assert(setup.source.get_kind() == 'local')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_preflight(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    assert(setup.source.get_kind() == 'local')

    # Just expect that this passes without throwing any exception
    setup.source.preflight()


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_preflight_fail(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    assert(setup.source.get_kind() == 'local')

    # Delete the file which the local source wants
    localfile = os.path.join(datafiles.dirname, datafiles.basename, 'file.txt')
    os.remove(localfile)

    # Expect a preflight error
    with pytest.raises(SourceError) as exc:
        setup.source.preflight()


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_unique_key(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    assert(setup.source.get_kind() == 'local')

    # Get the unique key
    unique_key = setup.source._get_unique_key()

    # No easy way to test this, let's just check that the
    # returned 'thing' is an array of tuples and the first element
    # of the first tuple is the filename, and the second is not falsy
    assert(isinstance(unique_key, list))
    assert(len(unique_key) == 1)
    filename, digest = unique_key[0]
    assert(filename == 'file.txt')
    assert(digest)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_stage_file(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    assert(setup.source.get_kind() == 'local')

    setup.source.stage(setup.context.builddir)
    assert(os.path.exists(os.path.join(setup.context.builddir, 'file.txt')))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'directory'))
def test_stage_directory(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    assert(setup.source.get_kind() == 'local')

    setup.source.stage(setup.context.builddir)
    assert(os.path.exists(os.path.join(setup.context.builddir, 'file.txt')))
    assert(os.path.exists(os.path.join(setup.context.builddir, 'subdir', 'anotherfile.txt')))
