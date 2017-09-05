import os
import pytest
from tests.testutils import cli, create_repo, ALL_REPO_KINDS
from tests.testutils.site import HAVE_OSTREE

from buildstream import _yaml

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_track(cli, tmpdir, datafiles, kind):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')
    element_name = 'track-test-{}.bst'.format(kind)

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    ref = repo.create(dev_files_path)

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config()
        ]
    }
    _yaml.dump(element,
               os.path.join(element_path,
                            element_name))

    # Assert that a fetch is needed
    assert cli.get_element_state(project, element_name) == 'no reference'

    # Now first try to track it
    result = cli.run(project=project, args=['track', element_name])
    assert result.exit_code == 0

    # And now fetch it: The Source has probably already cached the
    # latest ref locally, but it is not required to have cached
    # the associated content of the latest ref at track time, that
    # is the job of fetch.
    result = cli.run(project=project, args=['fetch', element_name])
    assert result.exit_code == 0

    # Assert that we are now buildable because the source is
    # now cached.
    assert cli.get_element_state(project, element_name) == 'buildable'
