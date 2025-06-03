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
from contextlib import ExitStack
import pytest

from buildstream import utils, _yaml
from buildstream.exceptions import ErrorDomain
from buildstream._testing import cli_integration as cli  # pylint: disable=unused-import
from buildstream._testing._utils.site import HAVE_SANDBOX

from tests.testutils import (
    create_artifact_share,
    assert_shared,
    assert_not_shared,
)

pytestmark = pytest.mark.integration


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "cached-fail")


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_build_checkout_cached_fail(cli, datafiles):
    project = str(datafiles)
    checkout = os.path.join(cli.directory, "checkout")

    # Try to build it, this should result in a failure that contains the content
    result = cli.run(project=project, args=["build", "base-fail.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that it's cached in a failed artifact
    assert cli.get_element_state(project, "base-fail.bst") == "failed"

    # Now check it out
    result = cli.run(project=project, args=["artifact", "checkout", "base-fail.bst", "--directory", checkout])
    result.assert_success()

    # Check that the checkout contains the file created before failure
    filename = os.path.join(checkout, "foo")
    assert os.path.exists(filename)


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_build_depend_on_cached_fail(cli, datafiles):
    project = str(datafiles)

    # Try to build it, this should result in caching a failure to build dep
    result = cli.run(project=project, args=["build", "base-fail.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that it's cached in a failed artifact
    assert cli.get_element_state(project, "base-fail.bst") == "failed"

    # Now we should fail because we've a cached fail of dep
    result = cli.run(project=project, args=["build", "depends-on-base-fail-expect-foo.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that it's not yet built, since one of its dependencies isn't ready.
    assert cli.get_element_state(project, "depends-on-base-fail-expect-foo.bst") == "waiting"


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

    # Build without access to host tools, this will fail
    result1 = cli.run(
        project=project,
        args=["build", "base-success.bst"],
        env={"PATH": str(tmp_path.joinpath("bin"))},
    )
    result1.assert_task_error(ErrorDomain.SANDBOX, "unavailable-local-sandbox")
    assert cli.get_element_state(project, "base-success.bst") == "buildable"

    # When rebuilding, this should work
    result2 = cli.run(project=project, args=["build", "base-success.bst"])
    result2.assert_success()
    assert cli.get_element_state(project, "base-success.bst") == "cached"


# Tests that failed builds will be retried if --retry-failed is specified
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.parametrize("use_share", (False, True), ids=["local-cache", "pull-failed-artifact"])
@pytest.mark.parametrize("retry", (True, False), ids=["retry", "no-retry"])
@pytest.mark.parametrize("strict", (True, False), ids=["strict", "non-strict"])
def test_retry_failed(cli, tmpdir, datafiles, use_share, retry, strict):
    project = str(datafiles)

    # Use separate cache directories for each iteration of this test
    # even though we're using cli_integration
    #
    # Global nonstrict configuration ensures all commands will be non-strict
    cli.configure({"cachedir": cli.directory, "projects": {"test": {"strict": strict}}})

    with ExitStack() as stack:

        if use_share:
            share = stack.enter_context(create_artifact_share(os.path.join(str(tmpdir), "artifactshare")))
            cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})

        # Try to build it, this should result in caching a failure of the target
        result = cli.run(project=project, args=["build", "base-fail.bst"])
        result.assert_main_error(ErrorDomain.STREAM, None)

        # Assert that it's cached in a failed artifact
        assert cli.get_element_state(project, "base-fail.bst") == "failed"

        if use_share:
            # Delete the local cache, provoke pulling of the failed build
            cli.remove_artifact_from_cache(project, "base-fail.bst")

            # Assert that the failed build has been removed
            assert cli.get_element_state(project, "base-fail.bst") == "buildable"

        # Even though we are in non-strict mode, the failed build should be retried
        if retry:
            result = cli.run(project=project, args=["build", "--retry-failed", "base-fail.bst"])
        else:
            result = cli.run(project=project, args=["build", "base-fail.bst"])

        # If we did not modify the cache key, we want to assert that we did not
        # in fact attempt to rebuild the failed artifact.
        #
        # Since the UX is very similar, we'll distinguish this by counting the number of
        # build logs which were produced.
        #
        result.assert_main_error(ErrorDomain.STREAM, None)
        if retry:
            assert "base-fail.bst" in result.get_built_elements()
            assert "base-fail.bst" in result.get_discarded_elements()
        else:
            assert "base-fail.bst" not in result.get_built_elements()
            assert "base-fail.bst" not in result.get_discarded_elements()

        if use_share:
            # Assert that we did indeed go through the motions of downloading the failed
            # build, and possibly discarded the failed artifact if the strong key did not match
            #
            assert "base-fail.bst" in result.get_pulled_elements()


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
@pytest.mark.parametrize("success", (True, False), ids=["success", "no-success"])
def test_nonstrict_retry_failed(cli, tmpdir, datafiles, use_share, success):
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

        # Regenerate the dependency so that the target would succeed to build
        if success:
            dep = generate_dep("foo", "intermediate.bst")
            _yaml.roundtrip_dump(dep, dep_path)

        # Even though we are in non-strict mode, the failed build should be retried
        result = cli.run(project=project, args=["build", "target.bst"])

        # Because the intermediate.bst is changed, the failed target.bst will be
        # retried unconditionally, assert that it gets discarded.
        #
        assert "target.bst" in result.get_discarded_elements()
        if success:
            result.assert_success()
        else:
            result.assert_main_error(ErrorDomain.STREAM, None)

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


# Test that we do not keep scheduling builds after one build fails
# with `--builders 1` and `--on-error quit`.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
def test_stop_building_after_failed(cli, datafiles):
    project = str(datafiles)

    # Since integration tests share a local artifact cache (for test performance, avoiding
    # downloading a runtime in every test), we reset the local cache state here by
    # deleting the two failing artifacts we are testing with
    #
    cli.remove_artifact_from_cache(project, "base-fail.bst")
    cli.remove_artifact_from_cache(project, "base-also-fail.bst")

    # Set only 1 builder, and explicitly configure `--on-error quit`
    cli.configure({"scheduler": {"builders": 1, "on-error": "quit"}})

    # Try to build it, this should result in only one failure
    result = cli.run(project=project, args=["build", "depends-on-two-failures.bst"])
    result.assert_main_error(ErrorDomain.STREAM, None)

    # Assert that out of the two elements, only one of them failed, the other one is
    # buildable because they both depend on base.bst which must have succeeded.
    states = cli.get_element_states(project, ["base-fail.bst", "base-also-fail.bst"], deps="none")
    assert "failed" in states.values()
    assert "buildable" in states.values()


# Test that we do push the failed build artifact, but we do not keep scheduling
# builds after one build fails with `--builders 1` and `--on-error quit`.
#
@pytest.mark.skipif(not HAVE_SANDBOX, reason="Only available with a functioning sandbox")
@pytest.mark.datafiles(DATA_DIR)
def test_push_but_stop_building_after_failed(cli, tmpdir, datafiles):
    project = str(datafiles)

    # Since integration tests share a local artifact cache (for test performance, avoiding
    # downloading a runtime in every test), we reset the local cache state here by
    # deleting the two failing artifacts we are testing with
    #
    cli.remove_artifact_from_cache(project, "base-fail.bst")
    cli.remove_artifact_from_cache(project, "base-also-fail.bst")

    with create_artifact_share(os.path.join(str(tmpdir), "remote")) as share:

        # Set only 1 builder, and explicitly configure `--on-error quit`
        cli.configure(
            {
                "scheduler": {"builders": 1, "on-error": "quit"},
                "artifacts": {"servers": [{"url": share.repo, "push": True}]},
            }
        )

        # Try to build it, this should result in only one failure
        result = cli.run(project=project, args=["build", "depends-on-two-failures.bst"])
        result.assert_main_error(ErrorDomain.STREAM, None)

        # Assert that out of the two elements, only one of them failed, the other one is
        # buildable because they both depend on base.bst which must have succeeded.
        states = cli.get_element_states(project, ["base-fail.bst", "base-also-fail.bst"], deps="none")
        assert "failed" in states.values()
        assert "buildable" in states.values()

        # Assert that the failed build is cached in a failed artifact, and that the other build
        # which would have failed, of course never made it to the artifact cache.
        for element_name, state in states.items():
            if state == "buildable":
                assert_not_shared(cli, share, project, element_name)
            elif state == "failed":
                assert_shared(cli, share, project, element_name)
            else:
                assert False, "Unreachable code reached !"
