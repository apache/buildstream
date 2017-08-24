import os
import pytest

from buildstream import SourceError

# import our common fixture
from .fixture import Setup

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'patch',
)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_create_source(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    patch_sources = [source for source in setup.sources if source.get_kind() == 'patch']
    assert(len(patch_sources) == 1)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_preflight(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    patch_source = [source for source in setup.sources if source.get_kind() == 'patch'][0]

    # Just expect that this passes without throwing any exception
    patch_source.preflight()


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_preflight_fail(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    patch_source = [source for source in setup.sources if source.get_kind() == 'patch'][0]

    # Delete the file which the local source wants
    localfile = os.path.join(datafiles.dirname, datafiles.basename, 'file_1.patch')
    os.remove(localfile)

    # Expect a preflight error
    with pytest.raises(SourceError):
        patch_source.preflight()


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_unique_key(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    patch_source = [source for source in setup.sources if source.get_kind() == 'patch'][0]

    # Get the unique key
    unique_key = patch_source.get_unique_key()

    # No easy way to test this, let's just check that the
    # returned 'thing' is an array of tuples and the first element
    # of the first tuple is the filename, and the second is not falsy
    assert(isinstance(unique_key, list))
    filename, digest, strip_level = unique_key
    assert(filename == 'file_1.patch')
    assert(digest)
    assert(strip_level == 1)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_stage_file(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)

    for source in setup.sources:
        source.preflight()
        source.stage(setup.context.builddir)
    with open(os.path.join(setup.context.builddir, 'file.txt')) as f:
        assert(f.read() == 'This is text file with superpowers\n')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_stage_file_nonexistent_dir(tmpdir, datafiles):
    setup = Setup(datafiles, 'failure-nonexistent-dir.bst', tmpdir)
    patch_sources = [source for source in setup.sources if source.get_kind() == 'patch']
    assert(len(patch_sources) == 1)

    for source in setup.sources:
        source.preflight()
        if source.get_kind() == 'patch':
            with pytest.raises(SourceError):
                source.stage(setup.context.builddir)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_stage_file_empty_dir(tmpdir, datafiles):
    setup = Setup(datafiles, 'failure-empty-dir.bst', tmpdir)
    patch_sources = [source for source in setup.sources if source.get_kind() == 'patch']
    assert(len(patch_sources) == 1)

    for source in setup.sources:
        source.preflight()
        if source.get_kind() == 'patch':
            with pytest.raises(SourceError):
                source.stage(setup.context.builddir)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'separate-patch-dir'))
def test_stage_separate_patch_dir(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    patch_sources = [source for source in setup.sources if source.get_kind() == 'patch']
    assert(len(patch_sources) == 1)

    for source in setup.sources:
        source.preflight()
        source.stage(setup.context.builddir)
    with open(os.path.join(setup.context.builddir, 'file.txt')) as f:
        assert(f.read() == 'This is text file in a directory with superpowers\n')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'multiple-patches'))
def test_stage_multiple_patches(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    patch_sources = [source for source in setup.sources if source.get_kind() == 'patch']
    assert(len(patch_sources) == 2)

    for source in setup.sources:
        source.preflight()
        source.stage(setup.context.builddir)
    with open(os.path.join(setup.context.builddir, 'file.txt')) as f:
        assert(f.read() == 'This is text file with more superpowers\n')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'different-strip-level'))
def test_patch_strip_level(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    patch_sources = [source for source in setup.sources if source.get_kind() == 'patch']
    assert(len(patch_sources) == 1)

    for source in setup.sources:
        source.preflight()
        source.stage(setup.context.builddir)
    with open(os.path.join(setup.context.builddir, 'file.txt')) as f:
        assert(f.read() == 'This is text file with superpowers\n')
