import os
import pytest
import subprocess

from buildstream import SourceError, LoadError, Consistency, PluginError

from tests.testutils.site import HAVE_BZR
from .fixture import Setup


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'bzr',
)


class BzrSetup(Setup):
    bzr_env = {"BZR_EMAIL": "Testy McTesterson <testy.mctesterson@example.com>"}

    def __init__(self, datafiles, bstfile, tmpdir):
        super().__init__(datafiles, bstfile, tmpdir)
        self.source.preflight()
        print("Host bzr is {}".format(self.source.host_bzr))

    def bzr_init(self, target_dir):
        self.source.call(['bzr', 'init', target_dir],
                         fail="Failed to initialize bzr branch at {}"
                              .format(target_dir),
                         env=self.bzr_env)

    def bzr_create(self, target_dir):
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        self.bzr_init(target_dir)

    def bzr_initrepo(self, target_dir):
        self.source.call(['bzr', 'init-repo', target_dir],
                         fail="Faile to init bzr repo at {}".format(target_dir),
                         env=self.bzr_env)

    def bzr_createrepo(self, target_dir):
        if not os.path.exist(target_dir):
            os.makedirs(target_dir)
        self.bzr_initrepo(target_dir)

    def bzr_commit(self, bzr_dir, filename):
        if not os.path.exists(bzr_dir):
            raise FileNotFoundError("{} doesn't exist!".format(bzr_dir))
        self.source.call(['bzr', 'add', filename], cwd=bzr_dir,
                         fail="Failed to add file {}".format(filename),
                         env=self.bzr_env)
        self.source.call(['bzr', 'commit', '--message="Add file {}"'.format(filename)],
                         cwd=bzr_dir,
                         fail="Failed to commit file {}".format(filename),
                         env=self.bzr_env)


# Test that the source can be parsed meaningfully.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
@pytest.mark.skipif(HAVE_BZR is False, reason="`bzr` is not available")
def test_create_source(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    assert(setup.source.get_kind() == 'bzr')
    assert(setup.source.url == 'http://www.example.com')
    assert(setup.source.get_ref() == 'foo')
    assert(setup.source.tracking == 'trunk')


# Test that without ref, consistency is set appropriately.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic-no-ref'))
@pytest.mark.skipif(HAVE_BZR is False, reason="`bzr` is not available")
def test_no_ref(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    assert(setup.source.get_consistency() == Consistency.INCONSISTENT)


# Test that with ref, consistency is resolved
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
@pytest.mark.skipif(HAVE_BZR is False, reason="`bzr` is not available")
def test_consistency_resolved(tmpdir, datafiles):
    setup = BzrSetup(datafiles, 'target.bst', tmpdir)
    assert(setup.source.get_consistency() == Consistency.RESOLVED)


# Test that with ref and fetching, consistency is cached
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
@pytest.mark.skipif(HAVE_BZR is False, reason="`bzr` is not available")
def test_consistency_cached(tmpdir, datafiles):
    setup = BzrSetup(datafiles, 'target.bst', tmpdir)
    repodir = os.path.join(str(datafiles), 'foo')
    branchdir = os.path.join(repodir, 'bar')
    setup.bzr_initrepo(repodir)
    setup.bzr_init(branchdir)
    setup.bzr_commit(branchdir, 'b')
    setup.bzr_commit(branchdir, 'c/d')
    setup.bzr_commit(branchdir, 'c/e')
    setup.source.fetch()

    found_consistency = setup.source.get_consistency()
    print("Consistency is {}".format(found_consistency))
    assert(found_consistency == Consistency.CACHED)


# Test that without track, consistency is set appropriately.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic-no-track'))
@pytest.mark.skipif(HAVE_BZR is False, reason="`bzr` is not available")
def test_no_track(tmpdir, datafiles):
    with pytest.raises(LoadError):
        setup = Setup(datafiles, 'target.bst', tmpdir)


# Test that when I fetch, it ends up in the cache.
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
@pytest.mark.skipif(HAVE_BZR is False, reason="`bzr` is not available")
def test_fetch(tmpdir, datafiles):
    # Pretty long setup
    setup = BzrSetup(datafiles, 'target.bst', tmpdir)
    repodir = os.path.join(str(datafiles), 'foo')
    branchdir = os.path.join(repodir, 'bar')
    setup.bzr_initrepo(repodir)
    setup.bzr_init(branchdir)
    setup.bzr_commit(branchdir, 'b')
    setup.bzr_commit(branchdir, 'c/d')
    setup.bzr_commit(branchdir, 'c/e')

    # Fetch the branch
    setup.source.fetch()
    assert(os.path.isdir(setup.source._get_mirror_dir()))
    assert(os.path.isdir(setup.source._get_branch_dir()))
    assert(os.path.isdir(os.path.join(setup.source._get_mirror_dir(), ".bzr")))


# Test that staging fails without ref
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
@pytest.mark.skipif(HAVE_BZR is False, reason="`bzr` is not available")
def test_stage_bad_ref(tmpdir, datafiles):
    # Pretty long setup
    setup = BzrSetup(datafiles, 'target-bad-ref.bst', tmpdir)
    repodir = os.path.join(str(datafiles), 'foo')
    branchdir = os.path.join(repodir, 'bar')
    setup.bzr_initrepo(repodir)
    setup.bzr_init(branchdir)
    setup.bzr_commit(branchdir, 'b')
    setup.bzr_commit(branchdir, 'c/d')
    setup.bzr_commit(branchdir, 'c/e')

    setup.source.fetch()
    stagedir = os.path.join(str(tmpdir), 'stage')

    with pytest.raises(PluginError):
        setup.source.stage(stagedir)


# Test that I can stage the repo successfully
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
@pytest.mark.skipif(HAVE_BZR is False, reason="`bzr` is not available")
def test_stage(tmpdir, datafiles):
    # Pretty long setup
    setup = BzrSetup(datafiles, 'target.bst', tmpdir)
    repodir = os.path.join(str(datafiles), 'foo')
    branchdir = os.path.join(repodir, 'bar')
    setup.bzr_initrepo(repodir)
    setup.bzr_init(branchdir)
    setup.bzr_commit(branchdir, 'b')
    setup.bzr_commit(branchdir, 'c/d')
    setup.bzr_commit(branchdir, 'c/e')

    setup.source.fetch()
    stagedir = os.path.join(str(tmpdir), 'stage')
    setup.source.stage(stagedir)
    expected_files = ['.bzr', 'b', 'c/d', 'c/e']
    for f in expected_files:
        dstpath = os.path.join(stagedir, f)
        print(dstpath)
        assert(os.path.exists(dstpath))


# Test that I can track the branch
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'fetch'))
@pytest.mark.skipif(HAVE_BZR is False, reason="`bzr` is not available")
def test_track(tmpdir, datafiles):
    # Pretty long setup
    setup = BzrSetup(datafiles, 'target-bad-ref.bst', tmpdir)
    repodir = os.path.join(str(datafiles), 'foo')
    branchdir = os.path.join(repodir, 'bar')
    setup.bzr_initrepo(repodir)
    setup.bzr_init(branchdir)
    setup.bzr_commit(branchdir, 'b')
    setup.bzr_commit(branchdir, 'c/d')
    setup.bzr_commit(branchdir, 'c/e')

    generated_ref = setup.source.track()
    print("Found ref {}".format(generated_ref))
    assert(generated_ref == '3')
