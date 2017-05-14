import os
import pytest
import tarfile

from buildstream import SourceError, Consistency

from .fixture import Setup

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'tar',
)


def _assemble_tar(workingdir, srcdir, dstfile):
    old_dir = os.getcwd()
    os.chdir(workingdir)
    with tarfile.open(dstfile, "w:gz") as tar:
        tar.add(srcdir)
    os.chdir(old_dir)


# Test that the source can be parsed meaningfully.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_create_source(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    assert(setup.source.get_kind() == 'tar')
    assert(setup.source.url == 'http://www.example.com')
    assert(setup.source.get_ref() == 'foo')


# Test that without ref, consistency is set appropriately.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'no-ref'))
def test_no_ref(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    assert(setup.source.get_consistency() == Consistency.INCONSISTENT)


# Test that when I fetch, it ends up in the cache.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
def test_fetch(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(str(datafiles), "a", src_tar)
    setup.source.ref = setup.source._sha256sum(src_tar)

    # Fetch the source
    setup.source.fetch()

    # File was fetched into mirror
    assert(os.path.isfile(setup.source._get_mirror_file()))

    # Fetched file is a tar
    assert(tarfile.is_tarfile(setup.source._get_mirror_file()))

    # Fetched file has the same contents as the source tar.
    with tarfile.open(src_tar) as tar:
        source_contents = tar.getnames()
    with tarfile.open(setup.source._get_mirror_file()) as tar:
        fetched_contents = tar.getnames()
    assert(source_contents == fetched_contents)


# Test that when I fetch a nonexistent URL, errors are handled gracefully.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
def test_fetch_bad_url(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    with pytest.raises(SourceError):
        setup.source.fetch()


# Test that when I fetch with an invalid ref, it fails.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
def test_fetch_bad_ref(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(str(datafiles), "a", src_tar)

    # Fetch the source
    with pytest.raises(SourceError):
        setup.source.fetch()


# Test that when I track, it gives me the sha256sum of the downloaded file.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'no-ref'))
def test_track(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(str(datafiles), "a", src_tar)
    tar_sha = setup.source._sha256sum(src_tar)

    assert(tar_sha == setup.source.track())


# Test that when tracking with a ref set, there is a warning
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
def test_track_with_ref(tmpdir, datafiles, capfd):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(str(datafiles), "a", src_tar)

    setup.source.track()
    out, _ = capfd.readouterr()
    assert("Potential man-in-the-middle attack!" in out)


def _list_dir_contents(srcdir):
    contents = set()
    for _, dirs, files in os.walk(srcdir):
        for d in dirs:
            contents.add(d)
        for f in files:
            contents.add(f)
    return contents


# Test that a staged checkout matches what was tarred up, with the default first subdir
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
def test_stage_default_basedir(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(str(datafiles), "a", src_tar)
    setup.source.ref = setup.source._sha256sum(src_tar)

    # Fetch the source
    setup.source.fetch()

    # Unpack the source
    stage_dir = os.path.join(str(tmpdir), "stage")
    os.makedirs(stage_dir)
    setup.source.stage(stage_dir)
    original_dir = os.path.join(str(datafiles), "a")
    stage_contents = _list_dir_contents(stage_dir)
    original_contents = _list_dir_contents(original_dir)
    assert(stage_contents == original_contents)


# Test that a staged checkout matches what was tarred up, with the full tarball
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'no-basedir'))
def test_stage_no_basedir(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    # Create a local tar
    src_tar = os.path.join(str(tmpdir), "a.tar.gz")
    _assemble_tar(str(datafiles), "a", src_tar)
    setup.source.ref = setup.source._sha256sum(src_tar)

    # Fetch the source
    setup.source.fetch()

    # Unpack the source
    stage_dir = os.path.join(str(tmpdir), "stage")
    os.makedirs(stage_dir)
    setup.source.stage(stage_dir)
    original_dir = os.path.join(str(datafiles), "a")
    stage_contents = _list_dir_contents(os.path.join(stage_dir, "a"))
    original_contents = _list_dir_contents(original_dir)
    assert(stage_contents == original_contents)
