import os
import pytest

from buildstream._exceptions import ErrorDomain
from buildstream.plugintestutils import cli_remote_execution as cli
from buildstream.plugintestutils.integration import assert_contains


pytestmark = pytest.mark.remoteexecution


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


# Test that `bst build` does not download file blobs of a build-only dependency
# to the local cache.
@pytest.mark.datafiles(DATA_DIR)
def test_build_dependency_partial_local_cas(cli, datafiles):
    project = str(datafiles)
    element_name = 'no-runtime-deps.bst'
    builddep_element_name = 'autotools/amhello.bst'
    checkout = os.path.join(cli.directory, 'checkout')
    builddep_checkout = os.path.join(cli.directory, 'builddep-checkout')

    services = cli.ensure_services()
    assert set(services) == set(['action-cache', 'execution', 'storage'])

    result = cli.run(project=project, args=['build', element_name])
    result.assert_success()

    # Verify that the target element is available in local cache
    result = cli.run(project=project, args=['artifact', 'checkout', element_name,
                                            '--directory', checkout])
    result.assert_success()
    assert_contains(checkout, ['/test'])

    # Verify that the build-only dependency is not (complete) in the local cache
    result = cli.run(project=project, args=['artifact', 'checkout', builddep_element_name,
                                            '--directory', builddep_checkout])
    result.assert_main_error(ErrorDomain.STREAM, 'uncached-checkout-attempt')
