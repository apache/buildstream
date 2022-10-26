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
#  Authors: Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#           Sam Thursfield <sam.thursfield@codethink.co.uk>
#           Jürg Billeter <juerg.billeter@codethink.co.uk>
#

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil
import pytest

from buildstream.exceptions import ErrorDomain
from buildstream._testing import cli, generate_project, Cli  # pylint: disable=unused-import
from buildstream._testing._utils.site import have_subsecond_mtime
from tests.testutils import (
    create_artifact_share,
    create_element_size,
    generate_junction,
    wait_for_cache_granularity,
    assert_shared,
    assert_not_shared,
)


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


# Tests that:
#
#  * `bst artifact push` fails if there are no remotes configured for pushing
#  * `bst artifact push` successfully pushes to any remote that is configured for pushing
#
@pytest.mark.datafiles(DATA_DIR)
def test_push(cli, tmpdir, datafiles):
    project = str(datafiles)

    # First build the project without the artifact cache configured
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()

    # Assert that we are now cached locally
    assert cli.get_element_state(project, "target.bst") == "cached"

    # Set up two artifact shares.
    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare1")) as share1:

        with create_artifact_share(os.path.join(str(tmpdir), "artifactshare2")) as share2:

            # Try pushing with no remotes configured. This should fail.
            result = cli.run(project=project, args=["artifact", "push", "target.bst"])
            result.assert_main_error(ErrorDomain.STREAM, None)

            # Configure bst to pull but not push from a cache and run `bst artifact push`.
            # This should also fail.
            cli.configure({"artifacts": {"servers": [{"url": share1.repo, "push": False}]}})
            result = cli.run(project=project, args=["artifact", "push", "target.bst"])
            result.assert_main_error(ErrorDomain.STREAM, None)

            # Configure bst to push to one of the caches and run `bst artifact push`. This works.
            cli.configure(
                {
                    "artifacts": {
                        "servers": [
                            {"url": share1.repo, "push": False},
                            {"url": share2.repo, "push": True},
                        ]
                    }
                }
            )
            cli.run(project=project, args=["artifact", "push", "target.bst"])

            assert_not_shared(cli, share1, project, "target.bst")
            assert_shared(cli, share2, project, "target.bst")

        # Now try pushing to both

        with create_artifact_share(os.path.join(str(tmpdir), "artifactshare2")) as share2:
            cli.configure(
                {
                    "artifacts": {
                        "servers": [
                            {"url": share1.repo, "push": True},
                            {"url": share2.repo, "push": True},
                        ]
                    }
                }
            )
            cli.run(project=project, args=["artifact", "push", "target.bst"])

            assert_shared(cli, share1, project, "target.bst")
            assert_shared(cli, share2, project, "target.bst")


# Tests `bst artifact push $artifact_ref`
@pytest.mark.datafiles(DATA_DIR)
def test_push_artifact(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), "cache")
    cli.configure({"cachedir": local_cache})

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        # First build it without the artifact cache configured
        result = cli.run(project=project, args=["build", element])
        result.assert_success()

        # Assert that the *artifact* is cached locally
        cache_key = cli.get_element_key(project, element)
        artifact_ref = os.path.join("test", os.path.splitext(element)[0], cache_key)
        assert os.path.exists(os.path.join(local_cache, "artifacts", "refs", artifact_ref))

        # Configure artifact share
        cli.configure(
            {
                #
                # FIXME: This test hangs "sometimes" if we allow
                #        concurrent push.
                #
                #        It's not too bad to ignore since we're
                #        using the local artifact cache functionality
                #        only, but it should probably be fixed.
                #
                "scheduler": {"pushers": 1},
                "artifacts": {
                    "servers": [
                        {
                            "url": share.repo,
                            "push": True,
                        }
                    ]
                },
            }
        )

        # Now try bst artifact push all the deps
        result = cli.run(project=project, args=["artifact", "push", artifact_ref])
        result.assert_success()

        # And finally assert that all the artifacts are in the share
        #
        # Note that assert shared tests that an element is shared by obtaining
        # the artifact ref and asserting that the path exists in the share
        assert_shared(cli, share, project, element)


@pytest.mark.datafiles(DATA_DIR)
def test_push_artifact_glob(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), "cache")
    cli.configure({"cachedir": local_cache})

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        # First build it without the artifact cache configured
        result = cli.run(project=project, args=["build", element])
        result.assert_success()

        # Assert that the *artifact* is cached locally
        cache_key = cli.get_element_key(project, element)
        artifact_ref = os.path.join("test", os.path.splitext(element)[0], cache_key)
        assert os.path.exists(os.path.join(local_cache, "artifacts", "refs", artifact_ref))

        # Configure artifact share
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})

        # Run bst artifact push with a wildcard, there is only one artifact
        # matching "test/target/*", even though it can be accessed both by it's
        # strong and weak key.
        #
        result = cli.run(project=project, args=["artifact", "push", "test/target/*"])
        result.assert_success()
        assert len(result.get_pushed_elements()) == 1


# Tests that:
#
#  * `bst artifact push` fails if the element is not cached locally
#  * `bst artifact push` fails if multiple elements are not cached locally
#
@pytest.mark.datafiles(DATA_DIR)
def test_push_fails(cli, tmpdir, datafiles):
    project = str(datafiles)

    # Set up the share
    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        # Configure bst to be able to push to the share
        cli.configure(
            {
                "artifacts": {
                    "servers": [
                        {"url": share.repo, "push": True},
                    ]
                }
            }
        )

        # First ensure that the target is *NOT* cache
        assert cli.get_element_state(project, "target.bst") != "cached"

        # Now try and push the target
        result = cli.run(project=project, args=["artifact", "push", "target.bst"])
        result.assert_main_error(ErrorDomain.STREAM, None)

        assert "Push failed: target.bst is not cached" in result.stderr

        # Now ensure that deps are also not cached
        assert cli.get_element_state(project, "import-bin.bst") != "cached"
        assert cli.get_element_state(project, "import-dev.bst") != "cached"
        assert cli.get_element_state(project, "compose-all.bst") != "cached"


# Tests that:
#
#  * `bst artifact push` fails when one of the targets is not cached, but still pushes the others
#
@pytest.mark.datafiles(DATA_DIR)
def test_push_fails_with_on_error_continue(cli, tmpdir, datafiles):
    project = str(datafiles)

    # Set up the share
    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        # First build the target (and its deps)
        result = cli.run(project=project, args=["build", "target.bst"])
        assert cli.get_element_state(project, "target.bst") == "cached"
        assert cli.get_element_state(project, "import-dev.bst") == "cached"

        # Now delete the artifact of a dependency and ensure it is not in the cache
        result = cli.run(project=project, args=["artifact", "delete", "import-dev.bst"])
        assert cli.get_element_state(project, "import-dev.bst") != "cached"

        # Configure bst to be able to push to the share
        cli.configure(
            {
                "artifacts": {
                    "servers": [
                        {"url": share.repo, "push": True},
                    ]
                }
            }
        )

        # Now try and push the target with its deps using --on-error continue
        # and assert that push failed, but what could be pushed was pushed
        result = cli.run(
            project=project, args=["--on-error=continue", "artifact", "push", "--deps", "all", "target.bst"]
        )

        # The overall process should return as failed
        result.assert_main_error(ErrorDomain.STREAM, None)

        # We should still have pushed what we could
        assert_shared(cli, share, project, "import-bin.bst")
        assert_shared(cli, share, project, "compose-all.bst")
        assert_shared(cli, share, project, "target.bst")

        assert_not_shared(cli, share, project, "import-dev.bst")

        assert "Push failed: import-dev.bst is not cached" in result.stderr


# Tests that `bst artifact push --deps DEPS` pushes selected dependencies of
# the given element.
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "deps, expected_states",
    [
        ("build", [False, True, False]),
        ("none", [True, False, False]),
        ("run", [True, False, True]),
        ("all", [True, True, True]),
    ],
)
def test_push_deps(cli, tmpdir, datafiles, deps, expected_states):
    project = str(datafiles)
    target = "checkout-deps.bst"
    build_dep = "import-dev.bst"
    runtime_dep = "import-bin.bst"

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        # First build it without the artifact cache configured
        result = cli.run(project=project, args=["build", target])
        result.assert_success()

        # Configure artifact share
        cli.configure(
            {
                #
                # FIXME: This test hangs "sometimes" if we allow
                #        concurrent push.
                #
                #        It's not too bad to ignore since we're
                #        using the local artifact cache functionality
                #        only, but it should probably be fixed.
                #
                "scheduler": {"pushers": 1},
                "artifacts": {
                    "servers": [
                        {
                            "url": share.repo,
                            "push": True,
                        }
                    ]
                },
            }
        )

        # Now try bst artifact push all the deps
        result = cli.run(project=project, args=["artifact", "push", target, "--deps", deps])
        result.assert_success()

        # And finally assert that the selected artifacts are in the share
        states = []
        for element in (target, build_dep, runtime_dep):
            is_cached = share.get_artifact(cli.get_artifact_name(project, "test", element)) is not None
            states.append(is_cached)
        assert states == expected_states


# Tests that `bst artifact push --deps run $artifact_ref` fails
@pytest.mark.datafiles(DATA_DIR)
def test_push_artifacts_all_deps_fails(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "checkout-deps.bst"

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), "cache")
    cli.configure({"cachedir": local_cache})

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        # First build it without the artifact cache configured
        result = cli.run(project=project, args=["build", element])
        result.assert_success()

        # Assert that the *artifact* is cached locally
        cache_key = cli.get_element_key(project, element)
        artifact_ref = os.path.join("test", os.path.splitext(element)[0], cache_key)
        assert os.path.exists(os.path.join(local_cache, "artifacts", "refs", artifact_ref))

        # Configure artifact share
        cli.configure(
            {
                #
                # FIXME: This test hangs "sometimes" if we allow
                #        concurrent push.
                #
                #        It's not too bad to ignore since we're
                #        using the local artifact cache functionality
                #        only, but it should probably be fixed.
                #
                "scheduler": {"pushers": 1},
                "artifacts": {
                    "servers": [
                        {
                            "url": share.repo,
                            "push": True,
                        }
                    ]
                },
            }
        )

        # Now try bst artifact push all the deps
        result = cli.run(project=project, args=["artifact", "push", "--deps", "all", artifact_ref])
        result.assert_main_error(ErrorDomain.STREAM, "deps-not-supported")


# Tests that `bst build` won't push artifacts to the cache it just pulled from.
#
# Regression test for https://gitlab.com/BuildStream/buildstream/issues/233.
@pytest.mark.datafiles(DATA_DIR)
def test_push_after_pull(cli, tmpdir, datafiles):
    project = str(datafiles)

    # Set up two artifact shares.
    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare1")) as share1, create_artifact_share(
        os.path.join(str(tmpdir), "artifactshare2")
    ) as share2:

        # Set the scene: share1 has the artifact, share2 does not.
        #
        cli.configure(
            {
                "artifacts": {
                    "servers": [
                        {"url": share1.repo, "push": True},
                    ]
                }
            }
        )

        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_success()

        cli.remove_artifact_from_cache(project, "target.bst")

        assert_shared(cli, share1, project, "target.bst")
        assert_not_shared(cli, share2, project, "target.bst")
        assert cli.get_element_state(project, "target.bst") != "cached"

        # Now run the build again. Correct `bst build` behaviour is to download the
        # artifact from share1 but not push it back again.
        #
        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_success()
        assert "target.bst" in result.get_pulled_elements()
        assert "target.bst" not in result.get_pushed_elements()

        # Delete the artifact locally again.
        cli.remove_artifact_from_cache(project, "target.bst")

        # Now we add share2 into the mix as a second push remote. This time,
        # `bst build` should push to share2 after pulling from share1.
        cli.configure(
            {
                "artifacts": {
                    "servers": [
                        {"url": share1.repo, "push": True},
                        {"url": share2.repo, "push": True},
                    ]
                }
            }
        )
        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_success()
        assert "target.bst" in result.get_pulled_elements()
        assert "target.bst" in result.get_pushed_elements()


# Ensure that when an artifact's size exceeds available disk space
# the least recently pushed artifact is deleted in order to make room for
# the incoming artifact.
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_expires(cli, datafiles, tmpdir):
    project = str(datafiles)
    element_path = "elements"

    # Create an artifact share (remote artifact cache) in the tmpdir/artifactshare
    # Set a 22 MB quota
    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare"), quota=int(22e6)) as share:

        # Configure bst to push to the cache
        cli.configure(
            {
                "artifacts": {
                    "servers": [
                        {"url": share.repo, "push": True},
                    ]
                }
            }
        )

        # Create and build an element of 15 MB
        create_element_size("element1.bst", project, element_path, [], int(15e6))
        result = cli.run(project=project, args=["build", "element1.bst"])
        result.assert_success()

        # Create and build an element of 5 MB
        create_element_size("element2.bst", project, element_path, [], int(5e6))
        result = cli.run(project=project, args=["build", "element2.bst"])
        result.assert_success()

        # check that element's 1 and 2 are cached both locally and remotely
        states = cli.get_element_states(project, ["element1.bst", "element2.bst"])

        assert states == {
            "element1.bst": "cached",
            "element2.bst": "cached",
        }

        assert_shared(cli, share, project, "element1.bst")
        assert_shared(cli, share, project, "element2.bst")

        # Create and build another element of 5 MB (This will exceed the free disk space available)
        create_element_size("element3.bst", project, element_path, [], int(5e6))
        result = cli.run(project=project, args=["build", "element3.bst"])
        result.assert_success()

        # Ensure it is cached both locally and remotely
        assert cli.get_element_state(project, "element3.bst") == "cached"
        assert_shared(cli, share, project, "element3.bst")

        # Ensure element1 has been removed from the share
        assert_not_shared(cli, share, project, "element1.bst")
        # Ensure that elemen2 remains
        assert_shared(cli, share, project, "element2.bst")


# Test that a large artifact, whose size exceeds the quota, is not pushed
# to the remote share
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_too_large(cli, datafiles, tmpdir):
    project = str(datafiles)
    element_path = "elements"

    # Create an artifact share (remote cache) in tmpdir/artifactshare
    # Mock a file system with 5 MB total space
    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare"), quota=int(5e6)) as share:

        # Configure bst to push to the remote cache
        cli.configure(
            {
                "artifacts": {
                    "servers": [{"url": share.repo, "push": True}],
                }
            }
        )

        # Create and push a 3MB element
        create_element_size("small_element.bst", project, element_path, [], int(3e6))
        result = cli.run(project=project, args=["build", "small_element.bst"])
        result.assert_success()

        # Create and try to push a 6MB element.
        create_element_size("large_element.bst", project, element_path, [], int(6e6))
        result = cli.run(project=project, args=["build", "large_element.bst"])
        # This should fail; the server will refuse to store the CAS
        # blobs for the artifact, and then fail to find the files for
        # the uploaded artifact proto.
        #
        # FIXME: This should be extremely uncommon in practice, since
        # the artifact needs to be at least half the cache size for
        # this to happen. Nonetheless, a nicer error message would be
        # nice (perhaps we should just disallow uploading artifacts
        # that large).
        result.assert_main_error(ErrorDomain.STREAM, None)

        # Ensure that the small artifact is still in the share
        states = cli.get_element_states(project, ["small_element.bst", "large_element.bst"])
        assert states["small_element.bst"] == "cached"
        assert_shared(cli, share, project, "small_element.bst")

        # Ensure that the artifact is cached locally but NOT remotely
        assert states["large_element.bst"] == "cached"
        assert_not_shared(cli, share, project, "large_element.bst")


# Test that when an element is pulled recently, it is not considered the LRU element.
@pytest.mark.datafiles(DATA_DIR)
def test_recently_pulled_artifact_does_not_expire(cli, datafiles, tmpdir):
    project = str(datafiles)
    element_path = "elements"

    # The artifact expiry logic relies on mtime changes, in real life second precision
    # should be enough for this to work almost all the time, but test cases happen very
    # quickly, resulting in all artifacts having the same mtime.
    #
    # This test requires subsecond mtime to be reliable.
    #
    if not have_subsecond_mtime(project):
        pytest.skip("Filesystem does not support subsecond mtime precision: {}".format(project))

    # Create an artifact share (remote cache) in tmpdir/artifactshare
    # Set a 22 MB quota
    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare"), quota=int(22e6)) as share:

        # Configure bst to push to the cache
        cli.configure(
            {
                "artifacts": {
                    "servers": [{"url": share.repo, "push": True}],
                }
            }
        )

        # Create and build 2 elements, one 5 MB and one 15 MB.
        create_element_size("element1.bst", project, element_path, [], int(5e6))
        result = cli.run(project=project, args=["build", "element1.bst"])
        result.assert_success()

        create_element_size("element2.bst", project, element_path, [], int(15e6))
        result = cli.run(project=project, args=["build", "element2.bst"])
        result.assert_success()

        # Ensure they are cached locally
        states = cli.get_element_states(project, ["element1.bst", "element2.bst"])
        assert states == {
            "element1.bst": "cached",
            "element2.bst": "cached",
        }

        # Ensure that they have  been pushed to the cache
        assert_shared(cli, share, project, "element1.bst")
        assert_shared(cli, share, project, "element2.bst")

        # Pull the element1 from the remote cache (this should update its mtime).
        # Use a separate local cache for this to ensure the complete element is pulled.
        cli2_path = os.path.join(str(tmpdir), "cli2")
        cli2 = Cli(cli2_path)
        result = cli2.run(project=project, args=["artifact", "pull", "element1.bst", "--artifact-remote", share.repo])
        result.assert_success()

        # Ensure element1 is cached locally
        assert cli2.get_element_state(project, "element1.bst") == "cached"

        wait_for_cache_granularity()

        # Create and build the element3 (of 5 MB)
        create_element_size("element3.bst", project, element_path, [], int(5e6))
        result = cli.run(project=project, args=["build", "element3.bst"])
        result.assert_success()

        # Make sure it's cached locally and remotely
        assert cli.get_element_state(project, "element3.bst") == "cached"
        assert_shared(cli, share, project, "element3.bst")

        # Ensure that element2 was deleted from the share and element1 remains
        assert_not_shared(cli, share, project, "element2.bst")
        assert_shared(cli, share, project, "element1.bst")


@pytest.mark.datafiles(DATA_DIR)
def test_push_cross_junction(cli, tmpdir, datafiles):
    project = str(datafiles)
    subproject_path = os.path.join(project, "files", "sub-project")
    junction_path = os.path.join(project, "elements", "junction.bst")

    generate_junction(tmpdir, subproject_path, junction_path, store_ref=True)

    result = cli.run(project=project, args=["build", "junction.bst:import-etc.bst"])
    result.assert_success()

    assert cli.get_element_state(project, "junction.bst:import-etc.bst") == "cached"

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        cli.configure(
            {
                "artifacts": {
                    "servers": [{"url": share.repo, "push": True}],
                }
            }
        )
        cli.run(project=project, args=["artifact", "push", "junction.bst:import-etc.bst"])

        cache_key = cli.get_element_key(project, "junction.bst:import-etc.bst")
        assert share.get_artifact(cli.get_artifact_name(project, "subtest", "import-etc.bst", cache_key=cache_key))


@pytest.mark.datafiles(DATA_DIR)
def test_push_already_cached(caplog, cli, tmpdir, datafiles):
    project = str(datafiles)
    caplog.set_level(1)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})
        result = cli.run(project=project, args=["build", "target.bst"])

        result.assert_success()
        assert "SKIPPED Push" not in result.stderr

        result = cli.run(project=project, args=["artifact", "push", "target.bst"])

        result.assert_success()
        assert not result.get_pushed_elements(), "No elements should have been pushed since the cache was populated"
        assert "INFO    Remote ({}) already has ".format(share.repo) in result.stderr
        assert "SKIPPED Push" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("use_remote", [True, False], ids=["with_cli_remote", "without_cli_remote"])
@pytest.mark.parametrize("ignore_project", [True, False], ids=["ignore_project_caches", "include_project_caches"])
def test_build_remote_option(caplog, cli, tmpdir, datafiles, use_remote, ignore_project):
    project = str(datafiles)
    caplog.set_level(1)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare1")) as shareuser, create_artifact_share(
        os.path.join(str(tmpdir), "artifactshare2")
    ) as shareproject, create_artifact_share(os.path.join(str(tmpdir), "artifactshare3")) as sharecli:

        # Add shareproject repo url to project.conf
        with open(os.path.join(project, "project.conf"), "a", encoding="utf-8") as projconf:
            projconf.write("artifacts:\n- url: {}\n  push: True".format(shareproject.repo))

        # Configure shareuser remote in user conf
        cli.configure({"artifacts": {"servers": [{"url": shareuser.repo, "push": True}]}})

        args = ["build", "target.bst"]
        if use_remote:
            args += ["--artifact-remote", sharecli.repo]
        if ignore_project:
            args += ["--ignore-project-artifact-remotes"]

        result = cli.run(project=project, args=args)

        # Artifacts should have only been pushed to sharecli, as that was provided via the cli
        result.assert_success()
        all_elements = ["target.bst", "import-bin.bst", "compose-all.bst"]
        for element_name in all_elements:
            assert element_name in result.get_pushed_elements()

            # Test shared state of project recommended cache depending
            # on whether we decided to ignore project suggestions.
            #
            if ignore_project:
                assert_not_shared(cli, shareproject, project, element_name)
            else:
                assert_shared(cli, shareproject, project, element_name)

            # If we specified a remote on the command line, this replaces any remotes
            # specified in user configuration.
            #
            if use_remote:
                assert_not_shared(cli, shareuser, project, element_name)
                assert_shared(cli, sharecli, project, element_name)
            else:
                assert_shared(cli, shareuser, project, element_name)
                assert_not_shared(cli, sharecli, project, element_name)


# This test ensures that we are able to run `bst artifact push` in non strict mode
# and that we do not crash when trying to push elements even though they
# have not yet been pulled.
#
# This is a regression test for issue #990
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("buildtrees", [("buildtrees"), ("normal")])
def test_push_no_strict(caplog, cli, tmpdir, datafiles, buildtrees):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    caplog.set_level(1)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        cli.configure(
            {"artifacts": {"servers": [{"url": share.repo, "push": True}]}, "projects": {"test": {"strict": False}}}
        )

        # First get us a build
        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_success()

        # Now cause one of the dependenies to change their cache key
        #
        # Here we just add a file, causing the strong cache key of the
        # import-bin.bst element to change due to the local files it
        # imports changing.
        path = os.path.join(project, "files", "bin-files", "newfile")
        with open(path, "w", encoding="utf-8") as f:
            f.write("PONY !")

        # Now build again after having changed the dependencies
        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_success()

        # Now run `bst artifact push`.
        #
        # Optionally try it with --pull-buildtrees, since this causes
        # a pull queue to be added to the `push` command, the behavior
        # around this is different.
        args = []
        if buildtrees == "buildtrees":
            args += ["--pull-buildtrees"]
        args += ["artifact", "push", "--deps", "all", "target.bst"]
        result = cli.run(project=project, args=args)
        result.assert_success()


# Test that push works after rebuilding an incomplete artifact
# of a non-reproducible element.
@pytest.mark.datafiles(DATA_DIR)
def test_push_after_rebuild(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    generate_project(
        project,
        config={
            "element-path": "elements",
            "min-version": "2.0",
            "plugins": [{"origin": "local", "path": "plugins", "elements": ["randomelement"]}],
        },
    )

    # First build the element
    result = cli.run(project=project, args=["build", "random.bst"])
    result.assert_success()
    assert cli.get_element_state(project, "random.bst") == "cached"

    # Delete the artifact blobs but keep the artifact proto,
    # i.e., now we have an incomplete artifact
    casdir = os.path.join(cli.directory, "cas")
    shutil.rmtree(casdir)
    assert cli.get_element_state(project, "random.bst") != "cached"

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})

        # Now rebuild the element and push it
        result = cli.run(project=project, args=["build", "random.bst"])
        result.assert_success()
        assert result.get_pushed_elements() == ["random.bst"]
        assert cli.get_element_state(project, "random.bst") == "cached"


# Test that push after rebuilding a non-reproducible element updates the
# artifact on the server.
@pytest.mark.datafiles(DATA_DIR)
def test_push_update_after_rebuild(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    generate_project(
        project,
        config={
            "element-path": "elements",
            "min-version": "2.0",
            "plugins": [{"origin": "local", "path": "plugins", "elements": ["randomelement"]}],
        },
    )

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})

        # Build the element and push the artifact
        result = cli.run(project=project, args=["build", "random.bst"])
        result.assert_success()
        assert result.get_pushed_elements() == ["random.bst"]
        assert cli.get_element_state(project, "random.bst") == "cached"

        # Now delete the artifact and ensure it is not in the cache
        result = cli.run(project=project, args=["artifact", "delete", "random.bst"])
        assert cli.get_element_state(project, "random.bst") != "cached"

        # Now rebuild the element. Reset config to disable pulling.
        cli.config = None
        result = cli.run(project=project, args=["build", "random.bst"])
        result.assert_success()
        assert cli.get_element_state(project, "random.bst") == "cached"

        # Push the new build
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})
        result = cli.run(project=project, args=["artifact", "push", "random.bst"])
        assert result.get_pushed_elements() == ["random.bst"]
