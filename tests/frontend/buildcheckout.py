import os
import pytest
from tests.testutils import cli, create_repo, ALL_REPO_KINDS
from tests.testutils.site import HAVE_OSTREE

from buildstream import _yaml
from buildstream._pipeline import PipelineError

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


def strict_args(args, strict):
    if strict != "strict":
        return ['--no-strict'] + args
    return args


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict", [("strict"), ("non-strict")])
def test_build_checkout(datafiles, cli, strict):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkout = os.path.join(cli.directory, 'checkout')

    # First build it
    result = cli.run(project=project, args=strict_args(['build', 'target.bst'], strict))
    assert result.exit_code == 0

    # Assert that after a successful build, the builddir is empty
    builddir = os.path.join(cli.directory, 'build')
    assert os.path.isdir(builddir)
    assert not os.listdir(builddir)

    # Now check it out
    result = cli.run(project=project, args=strict_args([
        'checkout', 'target.bst', checkout
    ], strict))
    assert result.exit_code == 0

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, 'usr', 'bin', 'hello')
    assert os.path.exists(filename)

    # Check that the executable hello file is found in the checkout
    filename = os.path.join(checkout, 'usr', 'include', 'pony.h')
    assert os.path.exists(filename)


fetch_build_checkout_combos = \
    [("strict", kind) for kind in ALL_REPO_KINDS] + \
    [("non-strict", kind) for kind in ALL_REPO_KINDS]


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("strict,kind", fetch_build_checkout_combos)
def test_fetch_build_checkout(cli, tmpdir, datafiles, strict, kind):
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
    result = cli.run(project=project, args=strict_args(['build', element_name], strict))
    assert result.exit_code == 0
    assert cli.get_element_state(project, element_name) == 'cached'

    # Now check it out
    result = cli.run(project=project, args=strict_args([
        'checkout', element_name, checkout
    ], strict))
    assert result.exit_code == 0

    # Check that the pony.h include from files/dev-files exists
    filename = os.path.join(checkout, 'usr', 'include', 'pony.h')
    assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
def test_install_to_build(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element = 'installed-to-build.bst'

    # Attempt building the element
    # We expect this to throw an ElementError, since the element will
    # attempt to stage into /buildstream/build, which is not allowed.
    result = cli.run(project=project, args=strict_args(['build', element], True))
    assert result.exit_code != 0

    # While the error thrown is an ElementError, the pipeline picks up
    # the error and raises it as a PipelineError. Since we are testing
    # through the cli runner, we can't be more specific.
    assert result.exception
    assert isinstance(result.exception, PipelineError)
