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
import shutil
import stat
import pytest
from buildstream import utils, _yaml
from buildstream._testing import cli  # pylint: disable=unused-import
from buildstream._testing import create_repo
from tests.testutils import (
    create_artifact_share,
    create_split_share,
    generate_junction,
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
#  * `bst build` pushes all build elements to configured 'push' cache
#  * `bst artifact pull --deps DEPS` downloads necessary artifacts from the cache
#
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize(
    "deps, expected_states",
    [
        ("build", ("buildable", "cached", "buildable")),
        ("none", ("cached", "buildable", "buildable")),
        ("run", ("cached", "buildable", "cached")),
        ("all", ("cached", "cached", "cached")),
    ],
)
def test_push_pull_deps(cli, tmpdir, datafiles, deps, expected_states):
    project = str(datafiles)
    target = "checkout-deps.bst"
    build_dep = "import-dev.bst"
    runtime_dep = "import-bin.bst"
    all_elements = [target, build_dep, runtime_dep]

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        # First build the target element and push to the remote.
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})
        result = cli.run(project=project, args=["build", target])
        result.assert_success()

        # Assert that everything is now cached in the remote.
        for element_name in all_elements:
            assert_shared(cli, share, project, element_name)

        # Now we've pushed, delete the user's local artifact cache
        # directory and try to redownload it from the share
        #
        casdir = os.path.join(cli.directory, "cas")
        shutil.rmtree(casdir)
        artifactdir = os.path.join(cli.directory, "artifacts")
        shutil.rmtree(artifactdir)

        # Assert that nothing is cached locally anymore
        states = cli.get_element_states(project, all_elements)
        assert not any(states[e] == "cached" for e in all_elements)

        # Now try bst artifact pull
        result = cli.run(project=project, args=["artifact", "pull", "--deps", deps, target])
        result.assert_success()

        # And assert that the pulled elements are again in the local cache
        states = cli.get_element_states(project, all_elements)
        states_flattended = (states[target], states[build_dep], states[runtime_dep])
        assert states_flattended == expected_states


# Tests that:
#
#  * `bst build` pushes all build elements ONLY to configured 'push' cache
#  * `bst artifact pull` finds artifacts that are available only in the secondary cache
#
@pytest.mark.datafiles(DATA_DIR)
def test_pull_secondary_cache(cli, tmpdir, datafiles):
    project = str(datafiles)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare1")) as share1, create_artifact_share(
        os.path.join(str(tmpdir), "artifactshare2")
    ) as share2:

        # Build the target and push it to share2 only.
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
        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_success()

        assert_not_shared(cli, share1, project, "target.bst")
        assert_shared(cli, share2, project, "target.bst")

        # Delete the user's local artifact cache.
        casdir = os.path.join(cli.directory, "cas")
        shutil.rmtree(casdir)
        artifactdir = os.path.join(cli.directory, "artifacts")
        shutil.rmtree(artifactdir)

        # Assert that the element is not cached anymore.
        assert cli.get_element_state(project, "target.bst") != "cached"

        # Now try bst artifact pull
        result = cli.run(project=project, args=["artifact", "pull", "target.bst"])
        result.assert_success()

        # And assert that it's again in the local cache, without having built,
        # i.e. we found it in share2.
        assert cli.get_element_state(project, "target.bst") == "cached"


# Tests that:
#
#  * `bst artifact push --artifact-remote` pushes to the given remote, not one from the config
#  * `bst artifact pull --artifact-remote` pulls from the given remote
#
@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_specific_remote(cli, tmpdir, datafiles):
    project = str(datafiles)

    with create_artifact_share(os.path.join(str(tmpdir), "goodartifactshare")) as good_share, create_artifact_share(
        os.path.join(str(tmpdir), "badartifactshare")
    ) as bad_share:

        # Build the target so we have it cached locally only.
        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_success()

        state = cli.get_element_state(project, "target.bst")
        assert state == "cached"

        # Configure the default push location to be bad_share; we will assert that
        # nothing actually gets pushed there.
        cli.configure(
            {
                "artifacts": {
                    "servers": [
                        {"url": bad_share.repo, "push": True},
                    ]
                }
            }
        )

        # Now try `bst artifact push` to the good_share.
        result = cli.run(
            project=project, args=["artifact", "push", "target.bst", "--artifact-remote", good_share.repo]
        )
        result.assert_success()

        # Assert that all the artifacts are in the share we pushed
        # to, and not the other.
        assert_shared(cli, good_share, project, "target.bst")
        assert_not_shared(cli, bad_share, project, "target.bst")

        # Now we've pushed, delete the user's local artifact cache
        # directory and try to redownload it from the good_share.
        #
        casdir = os.path.join(cli.directory, "cas")
        shutil.rmtree(casdir)
        artifactdir = os.path.join(cli.directory, "artifacts")
        shutil.rmtree(artifactdir)

        result = cli.run(
            project=project, args=["artifact", "pull", "target.bst", "--artifact-remote", good_share.repo]
        )
        result.assert_success()

        # And assert that it's again in the local cache, without having built
        assert cli.get_element_state(project, "target.bst") == "cached"


# Tests that:
#
#  * In non-strict mode, dependency changes don't block artifact reuse
#
@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_non_strict(cli, tmpdir, datafiles):
    project = str(datafiles)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        # First build the target element and push to the remote.
        cli.configure(
            {"artifacts": {"servers": [{"url": share.repo, "push": True}]}, "projects": {"test": {"strict": False}}}
        )
        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_success()
        assert cli.get_element_state(project, "target.bst") == "cached"

        # Assert that everything is now cached in the remote.
        all_elements = ["target.bst", "import-bin.bst", "import-dev.bst", "compose-all.bst"]
        for element_name in all_elements:
            assert_shared(cli, share, project, element_name)

        # Now we've pushed, delete the user's local artifact cache
        # directory and try to redownload it from the share
        #
        casdir = os.path.join(cli.directory, "cas")
        shutil.rmtree(casdir)
        artifactdir = os.path.join(cli.directory, "artifacts")
        shutil.rmtree(artifactdir)

        # Assert that nothing is cached locally anymore
        for element_name in all_elements:
            assert cli.get_element_state(project, element_name) != "cached"

        # Add a file to force change in strict cache key of import-bin.bst
        with open(os.path.join(str(project), "files", "bin-files", "usr", "bin", "world"), "w", encoding="utf-8") as f:
            f.write("world")

        # Assert that the workspaced element requires a rebuild
        assert cli.get_element_state(project, "import-bin.bst") == "buildable"
        # Assert that the target is still waiting due to --no-strict
        assert cli.get_element_state(project, "target.bst") == "waiting"

        # Now try bst artifact pull
        result = cli.run(project=project, args=["artifact", "pull", "--deps", "all", "target.bst"])
        result.assert_success()

        # And assert that the target is again in the local cache, without having built
        assert cli.get_element_state(project, "target.bst") == "cached"


@pytest.mark.datafiles(DATA_DIR)
def test_push_pull_cross_junction(cli, tmpdir, datafiles):
    project = str(datafiles)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        subproject_path = os.path.join(project, "files", "sub-project")
        junction_path = os.path.join(project, "elements", "junction.bst")

        generate_junction(tmpdir, subproject_path, junction_path, store_ref=True)

        # First build the target element and push to the remote.
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})
        result = cli.run(project=project, args=["build", "junction.bst:import-etc.bst"])
        result.assert_success()
        assert cli.get_element_state(project, "junction.bst:import-etc.bst") == "cached"

        cache_dir = os.path.join(project, "cache", "cas")
        shutil.rmtree(cache_dir)
        artifact_dir = os.path.join(project, "cache", "artifacts")
        shutil.rmtree(artifact_dir)

        assert cli.get_element_state(project, "junction.bst:import-etc.bst") == "buildable"

        # Now try bst artifact pull
        result = cli.run(project=project, args=["artifact", "pull", "junction.bst:import-etc.bst"])
        result.assert_success()

        # And assert that it's again in the local cache, without having built
        assert cli.get_element_state(project, "junction.bst:import-etc.bst") == "cached"


def _test_pull_missing_blob(cli, project, index, storage):
    # First build the target element and push to the remote.
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()
    assert cli.get_element_state(project, "target.bst") == "cached"

    # Assert that everything is now cached in the remote.
    all_elements = ["target.bst", "import-bin.bst", "import-dev.bst", "compose-all.bst"]
    for element_name in all_elements:
        project_name = "test"
        artifact_name = cli.get_artifact_name(project, project_name, element_name)
        artifact_proto = index.get_artifact_proto(artifact_name)
        assert artifact_proto
        assert storage.get_cas_files(artifact_proto)

    # Now we've pushed, delete the user's local artifact cache
    # directory and try to redownload it from the share
    #
    casdir = os.path.join(cli.directory, "cas")
    shutil.rmtree(casdir)
    artifactdir = os.path.join(cli.directory, "artifacts")
    shutil.rmtree(artifactdir)

    # Assert that nothing is cached locally anymore
    for element_name in all_elements:
        assert cli.get_element_state(project, element_name) != "cached"

    # Now delete blobs in the remote without deleting the artifact ref.
    # This simulates scenarios with concurrent artifact expiry.
    remote_objdir = os.path.join(storage.repodir, "cas", "objects")
    shutil.rmtree(remote_objdir)

    # Now try bst build
    result = cli.run(project=project, args=["build", "target.bst"])
    result.assert_success()

    # Assert that no artifacts were pulled
    assert not result.get_pulled_elements()


@pytest.mark.datafiles(DATA_DIR)
def test_pull_missing_blob(cli, tmpdir, datafiles):
    project = str(datafiles)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})

        _test_pull_missing_blob(cli, project, share, share)


@pytest.mark.datafiles(DATA_DIR)
def test_pull_missing_blob_split_share(cli, tmpdir, datafiles):
    project = str(datafiles)

    indexshare = os.path.join(str(tmpdir), "indexshare")
    storageshare = os.path.join(str(tmpdir), "storageshare")

    with create_split_share(indexshare, storageshare) as (index, storage):
        cli.configure(
            {
                "artifacts": {
                    "servers": [
                        {"url": index.repo, "push": True, "type": "index"},
                        {"url": storage.repo, "push": True, "type": "storage"},
                    ]
                }
            }
        )

        _test_pull_missing_blob(cli, project, index, storage)


@pytest.mark.datafiles(DATA_DIR)
def test_pull_missing_local_blob(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    repo = create_repo("tar", str(tmpdir))
    repo.create(os.path.join(str(datafiles), "files"))
    element_dir = os.path.join(str(tmpdir), "elements")
    project = str(tmpdir)
    project_config = {
        "name": "pull-missing-local-blob",
        "min-version": "2.0",
        "element-path": "elements",
    }
    project_file = os.path.join(str(tmpdir), "project.conf")
    _yaml.roundtrip_dump(project_config, project_file)
    input_config = {
        "kind": "import",
        "sources": [repo.source_config()],
    }
    input_name = "input.bst"
    input_file = os.path.join(element_dir, input_name)
    _yaml.roundtrip_dump(input_config, input_file)

    depends_name = "depends.bst"
    depends_config = {"kind": "stack", "depends": [input_name]}
    depends_file = os.path.join(element_dir, depends_name)
    _yaml.roundtrip_dump(depends_config, depends_file)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        # First build the import-bin element and push to the remote.
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})

        result = cli.run(project=project, args=["source", "track", input_name])
        result.assert_success()
        result = cli.run(project=project, args=["build", input_name])
        result.assert_success()
        assert cli.get_element_state(project, input_name) == "cached"

        # Delete a file blob from the local cache.
        # This is a placeholder to test partial CAS handling until we support
        # partial artifact pulling (or blob-based CAS expiry).
        #
        digest = utils.sha256sum(os.path.join(project, "files", "bin-files", "usr", "bin", "hello"))
        objpath = os.path.join(cli.directory, "cas", "objects", digest[:2], digest[2:])
        os.unlink(objpath)

        # Now try bst build
        result = cli.run(project=project, args=["build", depends_name])
        result.assert_success()

        # Assert that the import-bin artifact was pulled (completing the partial artifact)
        assert result.get_pulled_elements() == [input_name]


@pytest.mark.datafiles(DATA_DIR)
def test_pull_missing_notifies_user(caplog, cli, tmpdir, datafiles):
    project = str(datafiles)
    caplog.set_level(1)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        cli.configure({"artifacts": {"servers": [{"url": share.repo}]}})
        result = cli.run(project=project, args=["build", "target.bst"])

        result.assert_success()
        assert not result.get_pulled_elements(), "No elements should have been pulled since the cache was empty"

        assert "INFO    Remote ({}) does not have".format(share.repo) in result.stderr
        assert "SKIPPED Pull" in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_build_remote_option(caplog, cli, tmpdir, datafiles):
    project = str(datafiles)
    caplog.set_level(1)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare1")) as shareuser, create_artifact_share(
        os.path.join(str(tmpdir), "artifactshare2")
    ) as sharecli:

        # Configure shareuser remote in user conf
        cli.configure({"artifacts": {"servers": [{"url": shareuser.repo, "push": True}]}})

        # Push the artifacts to the shareuser remote.
        # Assert that shareuser has the artfifacts cached, but sharecli doesn't,
        # then delete locally cached elements
        result = cli.run(project=project, args=["build", "target.bst"])
        result.assert_success()
        all_elements = ["target.bst", "import-bin.bst", "compose-all.bst"]
        for element_name in all_elements:
            assert element_name in result.get_pushed_elements()
            assert_not_shared(cli, sharecli, project, element_name)
            assert_shared(cli, shareuser, project, element_name)
            cli.remove_artifact_from_cache(project, element_name)

        # Now check that a build with cli set as sharecli results in nothing being pulled,
        # as it doesn't have them cached and shareuser should be ignored. This
        # will however result in the artifacts being built and pushed to it
        result = cli.run(project=project, args=["build", "--artifact-remote", sharecli.repo, "target.bst"])
        result.assert_success()
        for element_name in all_elements:
            assert element_name not in result.get_pulled_elements()
            assert_shared(cli, sharecli, project, element_name)
            cli.remove_artifact_from_cache(project, element_name)

        # Now check that a clean build with cli set as sharecli should result in artifacts only
        # being pulled from it, as that was provided via the cli and is populated
        result = cli.run(project=project, args=["build", "--artifact-remote", sharecli.repo, "target.bst"])
        result.assert_success()
        for element_name in all_elements:
            assert cli.get_element_state(project, element_name) == "cached"
            assert element_name in result.get_pulled_elements()
        assert shareuser.repo not in result.stderr
        assert sharecli.repo in result.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_pull_access_rights(cli, tmpdir, datafiles):
    project = str(datafiles)
    checkout = os.path.join(str(tmpdir), "checkout")

    umask = utils.get_umask()

    # Work-around datafiles not preserving mode
    os.chmod(os.path.join(project, "files/bin-files/usr/bin/hello"), 0o0755)

    # We need a big file that does not go into a batch to test a different
    # code path
    os.makedirs(os.path.join(project, "files/dev-files/usr/share"), exist_ok=True)
    with open(os.path.join(project, "files/dev-files/usr/share/big-file"), "w", encoding="utf-8") as f:
        buf = " " * 4096
        for _ in range(1024):
            f.write(buf)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})
        result = cli.run(project=project, args=["build", "compose-all.bst"])
        result.assert_success()

        result = cli.run(
            project=project,
            args=["artifact", "checkout", "--no-integrate", "compose-all.bst", "--directory", checkout],
        )
        result.assert_success()

        st = os.lstat(os.path.join(checkout, "usr/include/pony.h"))
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o0666 & ~umask

        st = os.lstat(os.path.join(checkout, "usr/bin/hello"))
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o0777 & ~umask

        st = os.lstat(os.path.join(checkout, "usr/share/big-file"))
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o0666 & ~umask

        shutil.rmtree(checkout)

        casdir = os.path.join(cli.directory, "cas")
        shutil.rmtree(casdir)

        result = cli.run(project=project, args=["artifact", "pull", "compose-all.bst"])
        result.assert_success()

        result = cli.run(
            project=project,
            args=["artifact", "checkout", "--no-integrate", "compose-all.bst", "--directory", checkout],
        )
        result.assert_success()

        st = os.lstat(os.path.join(checkout, "usr/include/pony.h"))
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o0666 & ~umask

        st = os.lstat(os.path.join(checkout, "usr/bin/hello"))
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o0777 & ~umask

        st = os.lstat(os.path.join(checkout, "usr/share/big-file"))
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o0666 & ~umask


# Tests `bst artifact pull $artifact_ref`
@pytest.mark.datafiles(DATA_DIR)
def test_pull_artifact(cli, tmpdir, datafiles):
    project = str(datafiles)
    element = "target.bst"

    # Configure a local cache
    local_cache = os.path.join(str(tmpdir), "cache")
    cli.configure({"cachedir": local_cache})

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        # First build the target element and push to the remote.
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})

        result = cli.run(project=project, args=["build", element])
        result.assert_success()

        # Assert that the *artifact* is cached locally
        cache_key = cli.get_element_key(project, element)
        artifact_ref = os.path.join("test", os.path.splitext(element)[0], cache_key)
        assert os.path.exists(os.path.join(local_cache, "artifacts", "refs", artifact_ref))

        # Assert that the target is shared (note that assert shared will use the artifact name)
        assert_shared(cli, share, project, element)

        # Now we've pushed, remove the local cache
        shutil.rmtree(os.path.join(local_cache, "artifacts"))

        # Assert that nothing is cached locally anymore
        assert not os.path.exists(os.path.join(local_cache, "artifacts", "refs", artifact_ref))

        # Now try bst artifact pull
        result = cli.run(project=project, args=["artifact", "pull", artifact_ref])
        result.assert_success()

        # And assert that it's again in the local cache, without having built
        assert os.path.exists(os.path.join(local_cache, "artifacts", "refs", artifact_ref))


@pytest.mark.datafiles(DATA_DIR)
def test_dynamic_build_plan(cli, tmpdir, datafiles):
    project = str(datafiles)
    target = "checkout-deps.bst"
    build_dep = "import-dev.bst"
    runtime_dep = "import-bin.bst"
    all_elements = [target, build_dep, runtime_dep]

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare")) as share:

        # First build the target element and push to the remote.
        cli.configure({"artifacts": {"servers": [{"url": share.repo, "push": True}]}})
        result = cli.run(project=project, args=["build", target])
        result.assert_success()

        # Assert that everything is now cached in the remote.
        for element_name in all_elements:
            assert_shared(cli, share, project, element_name)

        # Now we've pushed, delete the user's local artifact cache directory
        casdir = os.path.join(cli.directory, "cas")
        shutil.rmtree(casdir)
        artifactdir = os.path.join(cli.directory, "artifacts")
        shutil.rmtree(artifactdir)

        # Assert that nothing is cached locally anymore
        states = cli.get_element_states(project, all_elements)
        assert not any(states[e] == "cached" for e in all_elements)

        # Now try to rebuild target
        result = cli.run(project=project, args=["build", target])
        result.assert_success()

        # Assert that target and runtime dependency were pulled
        # but build dependency was not pulled as it wasn't needed
        # (dynamic build plan).
        assert target in result.get_pulled_elements()
        assert runtime_dep in result.get_pulled_elements()
        assert build_dep not in result.get_pulled_elements()

        # And assert that the pulled elements are again in the local cache
        states = cli.get_element_states(project, all_elements)
        assert states[target] == "cached"
        assert states[runtime_dep] == "cached"
        assert states[build_dep] != "cached"
