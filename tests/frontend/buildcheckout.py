import os
import pytest
from tests.testutils.runcli import cli
from tests.testutils.repo import create_repo

from buildstream import _yaml

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.datafiles(DATA_DIR)
def test_build_checkout(datafiles, cli):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')

    # First build it
    result = cli.run(project=project, args=['build', 'target.bst'])
    assert result.exit_code == 0

    # Now check it out
    result = cli.run(project=project, args=[
        'checkout', 'target.bst', checkout
    ])
    assert result.exit_code == 0

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, 'usr', 'bin', 'hello')
    assert os.path.exists(filename)

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, 'usr', 'include', 'pony.h')
    assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", [('git'), ('bzr'), ('ostree'), ('tar')])
def test_fetch_build_checkout(cli, tmpdir, datafiles, kind):
    checkout = os.path.join(cli.directory, 'checkout')
    project = os.path.join(datafiles.dirname, datafiles.basename)
    dev_files_path = os.path.join(project, 'files', 'dev-files')
    element_path = os.path.join(project, 'elements')
    element_name = 'build-test-{}.bst'.format(kind)

    # Create our repo object of the given source type with
    # the dev files, and then collect the initial ref.
    #
    repo = create_repo(kind, str(tmpdir))
    ref = repo.create(dev_files_path)

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

    assert cli.get_element_state(project, element_name) == 'fetch needed'
    result = cli.run(project=project, args=['build', element_name])
    assert result.exit_code == 0
    assert cli.get_element_state(project, element_name) == 'cached'

    # Now check it out
    result = cli.run(project=project, args=[
        'checkout', element_name, checkout
    ])
    assert result.exit_code == 0

    # Check that the pony.h include from files/dev-files exists
    filename = os.path.join(checkout, 'usr', 'include', 'pony.h')
    assert os.path.exists(filename)
