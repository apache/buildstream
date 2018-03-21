import os
import pytest
from tests.testutils import cli, create_repo, ALL_REPO_KINDS

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, 'project')


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_fetch(cli, tmpdir, datafiles, kind):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    bin_files_path = os.path.join(project, 'files', 'bin-files')
    element_path = os.path.join(project, 'elements')
    element_name = 'fetch-test-{}.bst'.format(kind)

    # Create our repo object of the given source type with
    # the bin files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    ref = repo.create(bin_files_path)

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element,
               os.path.join(element_path,
                            element_name))

    # Assert that a fetch is needed
    assert cli.get_element_state(project, element_name) == 'fetch needed'

    # Now try to fetch it
    result = cli.run(project=project, args=['fetch', element_name])
    result.assert_success()

    # Assert that we are now buildable because the source is
    # now cached.
    assert cli.get_element_state(project, element_name) == 'buildable'


@pytest.mark.datafiles(os.path.join(TOP_DIR, 'consistencyerror'))
def test_fetch_consistency_error(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # When the error occurs outside of the scheduler at load time,
    # then the SourceError is reported directly as the main error.
    result = cli.run(project=project, args=['fetch', 'error.bst'])
    result.assert_main_error(ErrorDomain.SOURCE, 'the-consistency-error')


@pytest.mark.datafiles(os.path.join(TOP_DIR, 'consistencyerror'))
def test_fetch_consistency_bug(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # FIXME:
    #
    #    When a plugin raises an unhandled exception at load
    #    time, as is the case when running Source.get_consistency()
    #    for a fetch command, we could report this to the user
    #    more gracefully as a BUG message.
    #
    result = cli.run(project=project, args=['fetch', 'bug.bst'])
    assert result.exc is not None
    assert str(result.exc) == "Something went terribly wrong"
