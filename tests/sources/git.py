import os
import pytest

from buildstream._exceptions import ErrorDomain
from buildstream import _yaml

from tests.testutils import cli, create_repo
from tests.testutils.site import HAVE_GIT

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'git',
)


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_fetch_bad_ref(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Create the repo from 'repofiles' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project, 'repofiles'))

    # Write out our test target with a bad ref
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref='5')
        ]
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Assert that fetch raises an error here
    result = cli.run(project=project, args=[
        'fetch', 'target.bst'
    ])
    result.assert_main_error(ErrorDomain.PIPELINE, None)
    result.assert_task_error(ErrorDomain.SOURCE, None)


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_fetch_checkout(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo('git', str(tmpdir), 'subrepo')
    subref = subrepo.create(os.path.join(project, 'subrepofiles'))

    # Create the repo from 'repofiles' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project, 'repofiles'))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule('subdir', 'file://' + subrepo.repo)

    # Write out our test target with a bad ref
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Fetch, build, checkout
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Assert we checked out both files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, 'file.txt'))
    assert os.path.exists(os.path.join(checkoutdir, 'subdir', 'ponyfile.txt'))
