#
#  Copyright (C) 2016 Codethink Limited
#  Copyright (C) 2019 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream import utils, _yaml
from buildstream.exceptions import ErrorDomain
from buildstream.testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream.testing._utils.site import HAVE_SANDBOX

from tests.testutils import create_artifact_share


pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_build_checkout_cached_fail(cli, datafiles):
    project = str(datafiles)
    element_path = os.path.join(project, "elements", "element.bst")
    checkout = os.path.join(cli.directory, "checkout")

    # Write out our test target
    element = {
        "kind": "script",
        "depends": [{"filename": "base.bst", "type": "build",},],
        "config": {"commands": ["touch %{install-root}/foo", "false",],},
    }
    _yaml.roundtrip_dump(element, element_path)

    # Try to build it, this should result in a failure that contains the content
    result = cli.run(project=project, args=["build", "element.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that it's cached in a failed artifact
    assert cli.get_element_state(project, "element.bst") == "failed"

    # Now check it out
    result = cli.run(project=project, args=["artifact", "checkout", "element.bst", "--directory", checkout])
    result.assert_success()

    # Check that the checkout contains the file created before failure
    filename = os.path.join(checkout, "foo")
    assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_build_depend_on_cached_fail(cli, datafiles):
    project = str(datafiles)
    dep_path = os.path.join(project, "elements", "dep.bst")
    target_path = os.path.join(project, "elements", "target.bst")

    dep = {
        "kind": "script",
        "depends": [{"filename": "base.bst", "type": "build",},],
        "config": {"commands": ["touch %{install-root}/foo", "false",],},
    }
    _yaml.roundtrip_dump(dep, dep_path)
    target = {
        "kind": "script",
        "depends": [{"filename": "base.bst", "type": "build",}, {"filename": "dep.bst", "type": "build",},],
        "config": {"commands": ["test -e /foo",],},
    }
    _yaml.roundtrip_dump(target, target_path)

    # Try to build it, this should result in caching a failure to build dep
    result = cli.run(project=project, args=["build", "dep.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that it's cached in a failed artifact
    assert cli.get_element_state(project, "dep.bst") == "failed"

    # Now we should fail because we've a cached fail of dep
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that it's not yet built, since one of its dependencies isn't ready.
    assert cli.get_element_state(project, "target.bst") == "waiting"


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("on_error", ("continue", "quit"))
def test_push_cached_fail(cli, tmpdir, datafiles, on_error):
    if on_error == "quit":
        pytest.xfail("https://gitlab.com/BuildStream/buildstream/issues/534")

    project = str(datafiles)
    element_path = os.path.join(project, "elements", "element.bst")

    # Write out our test target
    element = {
        "kind": "script",
        "depends": [{"filename": "base.bst", "type": "build",},],
        "config": {
            "commands": [
                "false",
                # Ensure unique cache key for different test variants
                'TEST="{}"'.format(os.environ.get("PYTEST_CURRENT_TEST")),
            ],
        },
    }
    _yaml.roundtrip_dump(element, element_path)

    with create_artifact_share(os.path.join(str(tmpdir), "remote")) as share:
        cli.configure(
            {"artifacts": {"url": share.repo, "push": True},}
        )

        # Build the element, continuing to finish active jobs on error.
        result = cli.run(project=project, args=["--on-error={}".format(on_error), "build", "element.bst"])
        result.assert_main_error(ErrorDomain.STREAM, None)

        # This element should have failed
        assert cli.get_element_state(project, "element.bst") == "failed"
        # This element should have been pushed to the remote
        assert share.get_artifact(cli.get_artifact_name(project, "test", "element.bst"))


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("on_error", ("continue", "quit"))
def test_push_failed_missing_shell(cli, tmpdir, datafiles, on_error):
    """Test that we can upload a built artifact that didn't have a valid shell inside.

    When we don't have a valid shell, the artifact will be empty, not even the root directory.
    This ensures we handle the case of an entirely empty artifact correctly.
    """
    if on_error == "quit":
        pytest.xfail("https://gitlab.com/BuildStream/buildstream/issues/534")

    project = str(datafiles)
    element_path = os.path.join(project, "elements", "element.bst")

    # Write out our test target
    element = {
        "kind": "script",
        "config": {
            "commands": [
                "false",
                # Ensure unique cache key for different test variants
                'TEST="{}"'.format(os.environ.get("PYTEST_CURRENT_TEST")),
            ],
        },
    }
    _yaml.roundtrip_dump(element, element_path)

    with create_artifact_share(os.path.join(str(tmpdir), "remote")) as share:
        cli.configure(
            {"artifacts": {"url": share.repo, "push": True},}
        )

        # Build the element, continuing to finish active jobs on error.
        result = cli.run(project=project, args=["--on-error={}".format(on_error), "build", "element.bst"])
        result.assert_main_error(ErrorDomain.STREAM, None)

        # This element should have failed
        assert cli.get_element_state(project, "element.bst") == "failed"
        # This element should have been pushed to the remote
        assert share.get_artifact(cli.get_artifact_name(project, "test", "element.bst"))


@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_host_tools_errors_are_not_cached(cli, datafiles, tmp_path):
    # Create symlink to buildbox-casd to work with custom PATH
    buildbox_casd = tmp_path.joinpath("bin/buildbox-casd")
    buildbox_casd.parent.mkdir()
    os.symlink(utils.get_host_tool("buildbox-casd"), str(buildbox_casd))

    project = str(datafiles)
    element_path = os.path.join(project, "elements", "element.bst")

    # Write out our test target
    element = {
        "kind": "script",
        "depends": [{"filename": "base.bst", "type": "build",},],
        "config": {"commands": ["true",],},
    }
    _yaml.roundtrip_dump(element, element_path)

    # Build without access to host tools, this will fail
    result1 = cli.run(project=project, args=["build", "element.bst"], env={"PATH": str(tmp_path.joinpath("bin"))},)
    result1.assert_task_error(ErrorDomain.SANDBOX, "unavailable-local-sandbox")
    assert cli.get_element_state(project, "element.bst") == "buildable"

    # When rebuilding, this should work
    result2 = cli.run(project=project, args=["build", "element.bst"])
    result2.assert_success()
    assert cli.get_element_state(project, "element.bst") == "cached"
