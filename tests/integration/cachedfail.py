#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import glob
from contextlib import ExitStack
import pytest

from buildstream import utils, _yaml
from buildstream.exceptions import ErrorDomain
from buildstream._testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream._testing._utils.site import HAVE_SANDBOX

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
        "depends": [
            {
                "filename": "base.bst",
                "type": "build",
            },
        ],
        "config": {
            "commands": [
                "touch %{install-root}/foo",
                "false",
            ],
        },
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
        "depends": [
            {
                "filename": "base.bst",
                "type": "build",
            },
        ],
        "config": {
            "commands": [
                "touch %{install-root}/foo",
                "false",
            ],
        },
    }
    _yaml.roundtrip_dump(dep, dep_path)
    target = {
        "kind": "script",
        "depends": [
            {
                "filename": "base.bst",
                "type": "build",
            },
            {
                "filename": "dep.bst",
                "type": "build",
            },
        ],
        "config": {
            "commands": [
                "test -e /foo",
            ],
        },
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
    project = str(datafiles)
    element_path = os.path.join(project, "elements", "element.bst")

    # Write out our test target
    element = {
        "kind": "script",
        "depends": [
            {
                "filename": "base.bst",
                "type": "build",
            },
        ],
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
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})

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
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})

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
    os.symlink(utils._get_host_tool_internal("buildbox-casd", search_subprojects_dir="buildbox"), str(buildbox_casd))

    project = str(datafiles)
    element_path = os.path.join(project, "elements", "element.bst")

    # Write out our test target
    element = {
        "kind": "script",
        "depends": [
            {
                "filename": "base.bst",
                "type": "build",
            },
        ],
        "config": {
            "commands": [
                "true",
            ],
        },
    }
    _yaml.roundtrip_dump(element, element_path)

    # Build without access to host tools, this will fail
    result1 = cli.run(
        project=project,
        args=["build", "element.bst"],
        env={"PATH": str(tmp_path.joinpath("bin"))},
    )
    result1.assert_task_error(ErrorDomain.SANDBOX, "unavailable-local-sandbox")
    assert cli.get_element_state(project, "element.bst") == "buildable"

    # When rebuilding, this should work
    result2 = cli.run(project=project, args=["build", "element.bst"])
    result2.assert_success()
    assert cli.get_element_state(project, "element.bst") == "cached"


# Tests that failed builds will be retried in strict mode when dependencies have changed.
#
# This test ensures:
#   o Fixing a dependency such that the reverse dependency will succeed, gets automatically retried
#   o A subsequent retry of the same failed build will not trigger a retry attempt
#   o The same behavior is observed when a failed build artifact is downloaded from a remote cache
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.parametrize("use_share", (False, True), ids=["local-cache", "pull-failed-artifact"])
@pytest.mark.parametrize("retry", (True, False), ids=["retry", "no-retry"])
def test_nonstrict_retry_failed(cli, tmpdir, datafiles, use_share, retry):
    project = str(datafiles)
    intermediate_path = os.path.join(project, "elements", "intermediate.bst")
    dep_path = os.path.join(project, "elements", "dep.bst")
    target_path = os.path.join(project, "elements", "target.bst")

    # Use separate cache directories for each iteration of this test
    # even though we're using cli_integration
    #
    # Global nonstrict configuration ensures all commands will be non-strict
    cli.configure({"cachedir": cli.directory, "projects": {"test": {"strict": False}}})

    def generate_dep(filename, dependency):
        return {
            "kind": "manual",
            "depends": [dependency],
            "config": {
                "install-commands": [
                    "touch %{install-root}/" + filename,
                ],
            },
        }

    def generate_target():
        return {
            "kind": "manual",
            "depends": [
                "dep.bst",
            ],
            "config": {
                "build-commands": [
                    "test -e /foo",
                ],
            },
        }

    with ExitStack() as stack:

        if use_share:
            share = stack.enter_context(create_artifact_share(os.path.join(str(tmpdir), "artifactshare")))
            cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})

        intermediate = generate_dep("pony", "base.bst")
        dep = generate_dep("bar", "intermediate.bst")
        target = generate_target()
        _yaml.roundtrip_dump(intermediate, intermediate_path)
        _yaml.roundtrip_dump(dep, dep_path)
        _yaml.roundtrip_dump(target, target_path)

        # First build the dep / intermediate elements
        result = cli.run(project=project, args=["build", "dep.bst"])
        result.assert_success()

        # Remove the intermediate element from cache, rebuild the dep, such that only
        # a weak key for the dep is possible
        cli.remove_artifact_from_cache(project, "intermediate.bst")
        intermediate = generate_dep("horsy", "base.bst")
        _yaml.roundtrip_dump(intermediate, intermediate_path)

        result = cli.run(project=project, args=["build", "dep.bst"])
        result.assert_success()
        assert "dep.bst" not in result.get_built_elements()

        # Try to build it, this should result in caching a failure of the target
        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_main_error(ErrorDomain.STREAM, None)

        # Assert that it's cached in a failed artifact
        assert cli.get_element_state(project, "target.bst") == "failed"

        if use_share:
            # Delete the local cache, provoke pulling of the failed build
            cli.remove_artifact_from_cache(project, "target.bst")

            # Assert that the failed build has been removed
            assert cli.get_element_state(project, "target.bst") == "buildable"

        # Regenerate the dependency so that the target would succeed to build, if the
        # test is configured to test a retry
        if retry:
            dep = generate_dep("foo", "intermediate.bst")
            _yaml.roundtrip_dump(dep, dep_path)

        # Even though we are in non-strict mode, the failed build should be retried
        result = cli.run(project=project, args=["build", "target.bst"])

        # If we did not modify the cache key, we want to assert that we did not
        # in fact attempt to rebuild the failed artifact.
        #
        # Since the UX is very similar, we'll distinguish this by counting the number of
        # build logs which were produced.
        #
        logdir = os.path.join(cli.directory, "logs", "test", "target")
        build_logs = glob.glob("{}/*-build.*.log".format(logdir))
        if retry:
            result.assert_success()
            assert len(build_logs) == 2
        else:
            result.assert_main_error(ErrorDomain.STREAM, None)
            assert len(build_logs) == 1

        if use_share:
            # Assert that we did indeed go through the motions of downloading the failed
            # build, and possibly discarded the failed artifact if the strong key did not match
            #
            assert "target.bst" in result.get_pulled_elements()


# Tests that failed build artifacts in non-strict mode can be deleted.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_nonstrict_delete_failed(cli, tmpdir, datafiles):
    project = str(datafiles)
    intermediate_path = os.path.join(project, "elements", "intermediate.bst")
    dep_path = os.path.join(project, "elements", "dep.bst")
    target_path = os.path.join(project, "elements", "target.bst")

    # Global nonstrict configuration ensures all commands will be non-strict
    cli.configure({"projects": {"test": {"strict": False}}})

    def generate_dep(filename, dependency):
        return {
            "kind": "manual",
            "depends": [dependency],
            "config": {
                "install-commands": [
                    "touch %{install-root}/" + filename,
                ],
            },
        }

    def generate_target():
        return {
            "kind": "manual",
            "depends": [
                "dep.bst",
            ],
            "config": {
                "build-commands": [
                    "test -e /foo",
                ],
            },
        }

    intermediate = generate_dep("pony", "base.bst")
    dep = generate_dep("bar", "intermediate.bst")
    target = generate_target()
    _yaml.roundtrip_dump(intermediate, intermediate_path)
    _yaml.roundtrip_dump(dep, dep_path)
    _yaml.roundtrip_dump(target, target_path)

    # First build the dep / intermediate elements
    result = cli.run(project=project, args=["build", "dep.bst"])
    result.assert_success()

    # Remove the intermediate element from cache, rebuild the dep, such that only
    # a weak key for the dep is possible
    cli.remove_artifact_from_cache(project, "intermediate.bst")
    intermediate = generate_dep("horsy", "base.bst")
    _yaml.roundtrip_dump(intermediate, intermediate_path)

    result = cli.run(project=project, args=["build", "dep.bst"])
    result.assert_success()
    assert "dep.bst" not in result.get_built_elements()

    # Try to build it, this should result in caching a failure of the target
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that it's cached in a failed artifact
    assert cli.get_element_state(project, "target.bst") == "failed"

    # Delete it
    result = cli.run(project=project, args=["artifact", "delete", "target.bst"])

    # Assert that it's no longer cached, and returns to a buildable state
    assert cli.get_element_state(project, "target.bst") == "buildable"
