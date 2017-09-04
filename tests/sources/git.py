import os
import pytest
import tempfile
import subprocess

from buildstream import SourceError
from buildstream import utils

from tests.testutils.site import HAVE_GIT

# import our common fixture
from .fixture import Setup

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'git',
)


###############################################################
#                         Utilities                           #
###############################################################
# Derived setup which creates a target.bst with a git source
# and url pointing to a directory indicated by setup.origin_dir
#
class GitSetup(Setup):

    def __init__(self, datafiles, tmpdir, ref=None, track=None, bstfile=None):

        if not bstfile:
            bstfile = 'target.bst'

        # Where we get the project from
        directory = os.path.join(datafiles.dirname, datafiles.basename)

        # This is where we'll put gits
        self.origin_dir = os.path.join(str(tmpdir), 'origin')
        if not os.path.exists(self.origin_dir):
            os.mkdir(self.origin_dir)

        # Generate a target file with a file:// url in the tmpdir
        self.url = 'file://' + os.path.join(self.origin_dir, 'repo')
        self.generate_target_bst(directory, self.url, ref=ref, track=track, bstfile=bstfile)

        super().__init__(datafiles, bstfile, tmpdir)

    def generate_target_bst(self, directory, url, ref=None, track=None, bstfile=None):
        template = "kind: pony\n" + \
                   "description: This is the pony\n" + \
                   "sources:\n" + \
                   "- kind: git\n" + \
                   "  url: {url}\n"

        if track:
            template += "  track: {track}\n"
        if url:
            template += "  ref: {ref}\n"

        final = template.format(url=url, ref=ref, track=track)

        filename = os.path.join(directory, bstfile)
        with open(filename, 'w') as f:
            f.write(final)


class GitSubmoduleSetup(GitSetup):

    def generate_target_bst(self, directory, url, ref=None, track=None, bstfile=None):

        self.subrepo_url = 'file://' + os.path.join(self.origin_dir, 'subrepo')

        template = "kind: pony\n" + \
                   "description: This is the pony\n" + \
                   "sources:\n" + \
                   "- kind: git\n" + \
                   "  url: {url}\n"

        if track:
            template += "  track: {track}\n"
        if url:
            template += "  ref: {ref}\n"

        template += "submodules:\n" + \
                    "  subrepo:\n" + \
                    "    url: {subrepo}\n"

        final = template.format(url=url, ref=ref, track=track, subrepo=self.subrepo_url)

        filename = os.path.join(directory, bstfile)
        with open(filename, 'w') as f:
            f.write(final)


GIT_ENV = {
    'GIT_AUTHOR_DATE': '1320966000 +0200',
    'GIT_AUTHOR_NAME': 'tomjon',
    'GIT_AUTHOR_EMAIL': 'tom@jon.com',
    'GIT_COMMITTER_DATE': '1320966000 +0200',
    'GIT_COMMITTER_NAME': 'tomjon',
    'GIT_COMMITTER_EMAIL': 'tom@jon.com'
}


# Create a git repository at the setup.origin_dir
def git_create(setup, reponame):
    repodir = os.path.join(setup.origin_dir, reponame)
    os.mkdir(repodir)
    subprocess.call(['git', 'init', '.'], env=GIT_ENV, cwd=repodir)


# Add a file to the git
def git_add_file(setup, reponame, filename, content):
    repodir = os.path.join(setup.origin_dir, reponame)
    fullname = os.path.join(repodir, filename)
    with open(fullname, 'w') as f:
        f.write(content)

    # We rely on deterministic commit shas for testing, so set date and author
    subprocess.call(['git', 'add', filename], env=GIT_ENV, cwd=repodir)
    subprocess.call(['git', 'commit', '-m', 'Added the file'], env=GIT_ENV, cwd=repodir)


# Add a submodule to the git
def git_add_submodule(setup, reponame, url, path):
    repodir = os.path.join(setup.origin_dir, reponame)

    # We rely on deterministic commit shas for testing, so set date and author
    subprocess.call(['git', 'submodule', 'add', url, path], env=GIT_ENV, cwd=repodir)
    subprocess.call(['git', 'commit', '-m', 'Added the submodule'], env=GIT_ENV, cwd=repodir)


###############################################################
#                            Tests                            #
###############################################################
@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_create_source(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    assert(setup.source.get_kind() == 'git')


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_unique_key(tmpdir, datafiles):

    # Give it a ref of 12345
    setup = GitSetup(datafiles, tmpdir, '12345')
    assert(setup.source.get_kind() == 'git')

    # Check that the key has the ref we gave it, this isn't
    # much of a real test except it ensures that the fixture
    # we provided so far works
    unique_key = setup.source.get_unique_key()
    assert(unique_key[1] == '12345')


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_fetch(tmpdir, datafiles):

    # We know this is the right commit sha for the repo we create
    setup = GitSetup(datafiles, tmpdir, 'a3f9511fd3e4f043692f34234b4d2c7108de61fc')
    assert(setup.source.get_kind() == 'git')

    git_create(setup, 'repo')
    git_add_file(setup, 'repo', 'file.txt', 'pony')

    # Make sure we preflight first
    setup.source.preflight()

    # This should result in the mirror being created in the git sources dir
    setup.source.fetch()

    # Check that there is now a mirrored git repository at the expected directory
    directory_name = utils.url_directory_name(setup.url)
    fullpath = os.path.join(setup.context.sourcedir, 'git', directory_name)
    assert(os.path.isdir(fullpath))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_fetch_bad_ref(tmpdir, datafiles):

    # This is a bad ref, 5 is not the tree sha for the repo we're creating !
    setup = GitSetup(datafiles, tmpdir, '5')
    assert(setup.source.get_kind() == 'git')

    git_create(setup, 'repo')
    git_add_file(setup, 'repo', 'file.txt', 'pony')

    # Make sure we preflight first
    setup.source.preflight()

    # This should result result in an error, impossible to fetch ref '5'
    # from the origin since it doesnt exist.
    with pytest.raises(SourceError):
        setup.source.fetch()


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_stage(tmpdir, datafiles):

    # We know this is the right tree sha for the repo we create
    setup = GitSetup(datafiles, tmpdir, 'a3f9511fd3e4f043692f34234b4d2c7108de61fc')
    assert(setup.source.get_kind() == 'git')

    git_create(setup, 'repo')
    git_add_file(setup, 'repo', 'file.txt', 'pony')

    # Make sure we preflight and fetch first, cant stage without fetching
    setup.source.preflight()
    setup.source.fetch()

    # Stage the file and just check that it's there
    stagedir = os.path.join(setup.context.builddir, 'repo')
    setup.source.stage(stagedir)
    assert(os.path.exists(os.path.join(stagedir, 'file.txt')))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_fetch_new_ref_and_stage(tmpdir, datafiles):

    # This tests the functionality of already having a local mirror
    # but not yet having the ref which was asked for in the yaml
    #
    setup = GitSetup(datafiles, tmpdir, 'a3f9511fd3e4f043692f34234b4d2c7108de61fc')
    assert(setup.source.get_kind() == 'git')

    # This will get us the first ref
    git_create(setup, 'repo')
    git_add_file(setup, 'repo', 'file.txt', 'pony')

    # This will make a new ref available in the repo
    git_add_file(setup, 'repo', 'anotherfile.txt', 'pony')

    setup.source.preflight()
    setup.source.fetch()

    # Check that there is now a mirrored git repository at the expected directory
    directory_name = utils.url_directory_name(setup.url)
    fullpath = os.path.join(setup.context.sourcedir, 'git', directory_name)
    assert(os.path.isdir(fullpath))

    setup2 = GitSetup(datafiles, tmpdir, '3ac9cce94dd57e50a101e03dd6d43e0fc8a56b95', bstfile='another.bst')
    assert(setup2.source.get_kind() == 'git')
    setup2.source.preflight()
    setup2.source.fetch()

    # Stage the second source and just check that both files we created exist
    stagedir = os.path.join(setup.context.builddir, 'repo')
    setup2.source.stage(stagedir)
    assert(os.path.exists(os.path.join(stagedir, 'file.txt')))
    assert(os.path.exists(os.path.join(stagedir, 'anotherfile.txt')))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_track(tmpdir, datafiles):

    # Setup with the initial ref pointing to the first commit, but tracking master
    setup = GitSetup(datafiles, tmpdir, 'a3f9511fd3e4f043692f34234b4d2c7108de61fc', track='master')
    assert(setup.source.get_kind() == 'git')

    # Create the repo with the initial commit a3f9511fd3e4f043692f34234b4d2c7108de61fc
    git_create(setup, 'repo')
    git_add_file(setup, 'repo', 'file.txt', 'pony')

    # Add a new commit 3ac9cce94dd57e50a101e03dd6d43e0fc8a56b95
    git_add_file(setup, 'repo', 'anotherfile.txt', 'pony')

    setup.source.preflight()

    # Test that the new ref is the latest on master after tracking
    assert(setup.source.mirror.ref == 'a3f9511fd3e4f043692f34234b4d2c7108de61fc')
    new_ref = setup.source.track()
    assert(new_ref == '3ac9cce94dd57e50a101e03dd6d43e0fc8a56b95')


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_fetch(tmpdir, datafiles):

    # We cannot guess the submodule commit shas really, because we
    # need to encode the submodule uri in the commit which adds the
    # submodule, so let's use track() in this case.
    setup = GitSubmoduleSetup(datafiles, tmpdir, track='master')
    assert(setup.source.get_kind() == 'git')

    git_create(setup, 'repo')
    git_add_file(setup, 'repo', 'file.txt', 'pony')
    git_create(setup, 'subrepo')
    git_add_file(setup, 'subrepo', 'ponyfile.txt', 'file')
    git_add_submodule(setup, 'repo', setup.subrepo_url, 'subrepo')

    # Preflight, track and fetch
    setup.source.preflight()
    ref = setup.source.track()
    setup.source.set_ref(ref, setup.source._Source__origin_node)
    setup.source.fetch()

    # Check that there is now a mirrored git repository at the expected directory
    directory_name = utils.url_directory_name(setup.url)
    fullpath = os.path.join(setup.context.sourcedir, 'git', directory_name)
    assert(os.path.isdir(fullpath))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_stage(tmpdir, datafiles):

    # We cannot guess the submodule commit shas really, because we
    # need to encode the submodule uri in the commit which adds the
    # submodule, so let's use track() in this case.
    setup = GitSubmoduleSetup(datafiles, tmpdir, track='master')
    assert(setup.source.get_kind() == 'git')

    git_create(setup, 'repo')
    git_add_file(setup, 'repo', 'file.txt', 'pony')
    git_create(setup, 'subrepo')
    git_add_file(setup, 'subrepo', 'ponyfile.txt', 'file')
    git_add_submodule(setup, 'repo', setup.subrepo_url, 'subrepo')

    # Preflight, track and fetch
    setup.source.preflight()
    ref = setup.source.track()
    setup.source.set_ref(ref, setup.source._Source__origin_node)
    setup.source.fetch()

    # Stage the file and just check that it's there
    stagedir = os.path.join(setup.context.builddir, 'repo')
    setup.source.stage(stagedir)
    assert(os.path.exists(os.path.join(stagedir, 'file.txt')))

    # Assert the submodule file made it there
    assert(os.path.exists(os.path.join(stagedir, 'subrepo', 'ponyfile.txt')))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_fetch_new_ref_with_submodule(tmpdir, datafiles):

    # We know this is the right commit sha for the repo before adding a submodule
    setup = GitSetup(datafiles, tmpdir, 'a3f9511fd3e4f043692f34234b4d2c7108de61fc')
    assert(setup.source.get_kind() == 'git')

    git_create(setup, 'repo')
    git_add_file(setup, 'repo', 'file.txt', 'pony')

    setup.source.preflight()
    setup.source.fetch()

    # Check that there is now a mirrored git repository at the expected directory
    directory_name = utils.url_directory_name(setup.url)
    fullpath = os.path.join(setup.context.sourcedir, 'git', directory_name)
    assert(os.path.isdir(fullpath))

    # Now add another repo and add a commit to the main repo making the
    # other repo a submodule
    git_create(setup, 'subrepo')
    git_add_file(setup, 'subrepo', 'ponyfile.txt', 'file')
    subrepo_url = 'file://' + os.path.join(setup.origin_dir, 'subrepo')
    git_add_submodule(setup, 'repo', subrepo_url, 'subrepo')

    # This time we need to track and use master, we can't predict this commit sha
    #
    setup2 = GitSubmoduleSetup(datafiles, tmpdir, track='master', bstfile='another.bst')
    assert(setup.source.get_kind() == 'git')

    # Preflight, track and fetch
    setup2.source.preflight()
    ref = setup2.source.track()
    setup2.source.set_ref(ref, setup2.source._Source__origin_node)
    setup2.source.fetch()

    # Stage the file and just check that it's there
    stagedir = os.path.join(setup.context.builddir, 'repo')
    setup2.source.stage(stagedir)
    assert(os.path.exists(os.path.join(stagedir, 'file.txt')))

    # Assert the submodule file made it there
    assert(os.path.exists(os.path.join(stagedir, 'subrepo', 'ponyfile.txt')))
