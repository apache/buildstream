import os
import pytest
import tempfile
import subprocess

from buildstream import SourceError
from buildstream import utils

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

    def __init__(self, datafiles, tmpdir, ref, track=None, bstfile=None):

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
        self.generate_target_bst(directory, self.url, ref, track=track, bstfile=bstfile)

        super().__init__(datafiles, bstfile, tmpdir)

    def generate_target_bst(self, directory, url, ref, track=None, bstfile=None):
        template = "kind: pony\n" + \
                   "description: This is the pony\n" + \
                   "sources:\n" + \
                   "- kind: git\n" + \
                   "  url: {url}\n" + \
                   "  ref: {ref}\n"
        final = template.format(url=url, ref=ref)

        if track:
            final = final + "  track: {track}\n".format(track=track)

        filename = os.path.join(directory, bstfile)
        with open(filename, 'w') as f:
            f.write(final)


class GitSubmoduleSetup(GitSetup):

    def generate_target_bst(self, directory, url, ref, track=None, bstfile=None):

        template = "kind: pony\n" + \
                   "description: This is the pony\n" + \
                   "sources:\n" + \
                   "- kind: git\n" + \
                   "  url: {url}\n" + \
                   "  ref: {ref}\n" + \
                   "submodules:\n" + \
                   "  subrepo:\n" + \
                   "    url: {subrepo}\n"

        self.subrepo_url = 'file://' + os.path.join(self.origin_dir, 'subrepo')
        final = template.format(url=url, ref=ref, subrepo=self.subrepo_url)

        if track:
            final = final + "  track: {track}\n".format(track=track)

        filename = os.path.join(directory, bstfile)
        with open(filename, 'w') as f:
            f.write(final)


# Create a git repository at the setup.origin_dir
def git_create(setup, reponame):
    repodir = os.path.join(setup.origin_dir, reponame)
    os.mkdir(repodir)
    subprocess.call(['git', 'init', '.'], cwd=repodir)


# Add a file to the git
def git_add_file(setup, reponame, filename, content):
    repodir = os.path.join(setup.origin_dir, reponame)
    fullname = os.path.join(repodir, filename)
    with open(fullname, 'w') as f:
        f.write(content)

    # We rely on deterministic commit shas for testing, so set date and author
    subprocess.call(['git', 'add', filename], cwd=repodir)
    subprocess.call(['git', 'commit', '-m', 'Added the file'],
                    env={'GIT_AUTHOR_DATE': '1320966000 +0200',
                         'GIT_AUTHOR_NAME': 'tomjon',
                         'GIT_AUTHOR_EMAIL': 'tom@jon.com',
                         'GIT_COMMITTER_DATE': '1320966000 +0200',
                         'GIT_COMMITTER_NAME': 'tomjon',
                         'GIT_COMMITTER_EMAIL': 'tom@jon.com'},
                    cwd=repodir)


# Add a submodule to the git
def git_add_submodule(setup, reponame, url, path):
    repodir = os.path.join(setup.origin_dir, reponame)

    # We rely on deterministic commit shas for testing, so set date and author
    subprocess.call(['git', 'submodule', 'add', url, path], cwd=repodir)
    subprocess.call(['git', 'commit', '-m', 'Added the submodule'],
                    env={'GIT_AUTHOR_DATE': '1320966000 +0200',
                         'GIT_AUTHOR_NAME': 'tomjon',
                         'GIT_AUTHOR_EMAIL': 'tom@jon.com',
                         'GIT_COMMITTER_DATE': '1320966000 +0200',
                         'GIT_COMMITTER_NAME': 'tomjon',
                         'GIT_COMMITTER_EMAIL': 'tom@jon.com'},
                    cwd=repodir)


###############################################################
#                            Tests                            #
###############################################################
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'basic'))
def test_create_source(tmpdir, datafiles):
    setup = Setup(datafiles, 'target.bst', tmpdir)
    assert(setup.source.get_kind() == 'git')


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


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_refresh(tmpdir, datafiles):

    # Setup with the initial ref pointing to the first commit, but tracking master
    setup = GitSetup(datafiles, tmpdir, 'a3f9511fd3e4f043692f34234b4d2c7108de61fc', track='master')
    assert(setup.source.get_kind() == 'git')

    # Create the repo with the initial commit a3f9511fd3e4f043692f34234b4d2c7108de61fc
    git_create(setup, 'repo')
    git_add_file(setup, 'repo', 'file.txt', 'pony')

    # Add a new commit 3ac9cce94dd57e50a101e03dd6d43e0fc8a56b95
    git_add_file(setup, 'repo', 'anotherfile.txt', 'pony')

    setup.source.preflight()

    # Test that the ref has changed to latest on master after refreshing
    assert(setup.source.mirror.ref == 'a3f9511fd3e4f043692f34234b4d2c7108de61fc')
    setup.source.refresh(setup.source._Source__origin_node)
    assert(setup.source.mirror.ref == '3ac9cce94dd57e50a101e03dd6d43e0fc8a56b95')


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_fetch(tmpdir, datafiles):

    # We know this is the right commit sha for the repo we create
    setup = GitSubmoduleSetup(datafiles, tmpdir, 'e65c898f8b4a42024ced731def6a2f7bde0ea138')
    assert(setup.source.get_kind() == 'git')

    git_create(setup, 'repo')
    git_add_file(setup, 'repo', 'file.txt', 'pony')
    git_create(setup, 'subrepo')
    git_add_file(setup, 'subrepo', 'ponyfile.txt', 'file')
    git_add_submodule(setup, 'repo', setup.subrepo_url, 'subrepo')

    # Make sure we preflight first
    setup.source.preflight()

    # This should result in the mirror being created in the git sources dir
    setup.source.fetch()

    # Check that there is now a mirrored git repository at the expected directory
    directory_name = utils.url_directory_name(setup.url)
    fullpath = os.path.join(setup.context.sourcedir, 'git', directory_name)
    assert(os.path.isdir(fullpath))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_stage(tmpdir, datafiles):

    # We know this is the right commit sha for the repo we create
    setup = GitSubmoduleSetup(datafiles, tmpdir, 'cea8dbfe21eaa069c28094418afa55bf2223838f')
    assert(setup.source.get_kind() == 'git')

    git_create(setup, 'repo')
    git_add_file(setup, 'repo', 'file.txt', 'pony')
    git_create(setup, 'subrepo')
    git_add_file(setup, 'subrepo', 'ponyfile.txt', 'file')
    git_add_submodule(setup, 'repo', setup.subrepo_url, 'subrepo')

    # Make sure we preflight and fetch first
    setup.source.preflight()
    setup.source.fetch()

    # Stage the file and just check that it's there
    stagedir = os.path.join(setup.context.builddir, 'repo')
    setup.source.stage(stagedir)
    assert(os.path.exists(os.path.join(stagedir, 'file.txt')))

    # Assert the submodule file made it there
    assert(os.path.exists(os.path.join(stagedir, 'subrepo', 'ponyfile.txt')))


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_fetch_new_ref_with_submodule(tmpdir, datafiles):

    # We know this is the right commit sha for the repo we create
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

    setup2 = GitSubmoduleSetup(datafiles, tmpdir, '7b5a9a0da6752c5b9a3fe52055e016354cda704e',
                               bstfile='another.bst')
    assert(setup.source.get_kind() == 'git')

    setup2.source.preflight()
    setup2.source.fetch()

    # Stage the file and just check that it's there
    stagedir = os.path.join(setup.context.builddir, 'repo')
    setup2.source.stage(stagedir)
    assert(os.path.exists(os.path.join(stagedir, 'file.txt')))

    # Assert the submodule file made it there
    assert(os.path.exists(os.path.join(stagedir, 'subrepo', 'ponyfile.txt')))
