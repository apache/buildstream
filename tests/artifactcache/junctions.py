# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import shutil
import pytest

from buildstream import _yaml
from buildstream.testing import cli  # pylint: disable=unused-import

from tests.testutils import create_artifact_share, assert_shared, assert_not_shared


DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "junctions",)


def project_set_artifacts(project, url):
    project_conf_file = os.path.join(project, "project.conf")
    project_config = _yaml.load(project_conf_file, shortname=None)
    project_config["artifacts"] = {"url": url, "push": True}
    _yaml.roundtrip_dump(project_config.strip_node_info(), file=project_conf_file)


@pytest.mark.datafiles(DATA_DIR)
def test_push_pull(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "parent")
    base_project = os.path.join(str(project), "base")

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare-parent")) as share, create_artifact_share(
        os.path.join(str(tmpdir), "artifactshare-base")
    ) as base_share:

        # First build it without the artifact cache configured
        result = cli.run(project=project, args=["build", "target.bst"])
        assert result.exit_code == 0

        # Assert that we are now cached locally
        state = cli.get_element_state(project, "target.bst")
        assert state == "cached"
        state = cli.get_element_state(base_project, "base-element.bst")
        assert state == "cached"

        project_set_artifacts(project, share.repo)
        project_set_artifacts(base_project, base_share.repo)

        # Now try bst artifact push
        result = cli.run(project=project, args=["artifact", "push", "--deps", "all", "target.bst"])
        assert result.exit_code == 0

        # And finally assert that the artifacts are in the right shares
        #
        # In the parent project's cache
        assert_shared(cli, share, project, "target.bst", project_name="parent")
        assert_shared(cli, share, project, "app.bst", project_name="parent")
        assert_not_shared(cli, share, base_project, "base-element.bst", project_name="base")

        # In the junction project's cache
        assert_not_shared(cli, base_share, project, "target.bst", project_name="parent")
        assert_not_shared(cli, base_share, project, "app.bst", project_name="parent")
        assert_shared(cli, base_share, base_project, "base-element.bst", project_name="base")

        # Now we've pushed, delete the user's local artifact cache
        # directory and try to redownload it from the share
        #
        cas = os.path.join(cli.directory, "cas")
        shutil.rmtree(cas)
        artifact_dir = os.path.join(cli.directory, "artifacts")
        shutil.rmtree(artifact_dir)

        # Assert that nothing is cached locally anymore
        state = cli.get_element_state(project, "target.bst")
        assert state != "cached"
        state = cli.get_element_state(base_project, "base-element.bst")
        assert state != "cached"

        # Now try bst artifact pull
        result = cli.run(project=project, args=["artifact", "pull", "--deps", "all", "target.bst"])
        assert result.exit_code == 0

        # And assert that they are again in the local cache, without having built
        state = cli.get_element_state(project, "target.bst")
        assert state == "cached"
        state = cli.get_element_state(base_project, "base-element.bst")
        assert state == "cached"


@pytest.mark.datafiles(DATA_DIR)
def test_caching_junction_elements(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "parent")
    base_project = os.path.join(str(project), "base")

    # Load the junction element
    junction_element = os.path.join(project, "base.bst")
    junction_data = _yaml.roundtrip_load(junction_element)

    # Add the "cache-junction-elements" boolean to the junction Element
    junction_data["config"] = {"cache-junction-elements": True}
    _yaml.roundtrip_dump(junction_data, junction_element)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare-parent")) as share, create_artifact_share(
        os.path.join(str(tmpdir), "artifactshare-base")
    ) as base_share:

        # First build it without the artifact cache configured
        result = cli.run(project=project, args=["build", "target.bst"])
        assert result.exit_code == 0

        # Assert that we are now cached locally
        state = cli.get_element_state(project, "target.bst")
        assert state == "cached"
        state = cli.get_element_state(base_project, "base-element.bst")
        assert state == "cached"

        project_set_artifacts(project, share.repo)
        project_set_artifacts(base_project, base_share.repo)

        # Now try bst artifact push
        result = cli.run(project=project, args=["artifact", "push", "--deps", "all", "target.bst"])
        assert result.exit_code == 0

        # And finally assert that the artifacts are in the right shares
        #
        # The parent project's cache should *also* contain elements from the junction
        assert_shared(cli, share, project, "target.bst", project_name="parent")
        assert_shared(cli, share, project, "app.bst", project_name="parent")
        assert_shared(cli, share, base_project, "base-element.bst", project_name="base")

        # The junction project's cache should only contain elements in the junction project
        assert_not_shared(cli, base_share, project, "target.bst", project_name="parent")
        assert_not_shared(cli, base_share, project, "app.bst", project_name="parent")
        assert_shared(cli, base_share, base_project, "base-element.bst", project_name="base")


@pytest.mark.datafiles(DATA_DIR)
def test_ignore_junction_remotes(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "parent")
    base_project = os.path.join(str(project), "base")

    # Load the junction element
    junction_element = os.path.join(project, "base.bst")
    junction_data = _yaml.roundtrip_load(junction_element)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare-parent")) as share, create_artifact_share(
        os.path.join(str(tmpdir), "artifactshare-base")
    ) as base_share:

        # Immediately declare the artifact caches in the appropriate project configs
        project_set_artifacts(project, share.repo)
        project_set_artifacts(base_project, base_share.repo)

        # Build and populate the project remotes with their respective elements
        result = cli.run(project=project, args=["build", "target.bst"])
        assert result.exit_code == 0

        # And finally assert that the artifacts are in the right shares
        #
        # The parent project's cache should only contain project elements
        assert_shared(cli, share, project, "target.bst", project_name="parent")
        assert_shared(cli, share, project, "app.bst", project_name="parent")
        assert_not_shared(cli, share, base_project, "base-element.bst", project_name="base")

        # The junction project's cache should only contain elements in the junction project
        assert_not_shared(cli, base_share, project, "target.bst", project_name="parent")
        assert_not_shared(cli, base_share, project, "app.bst", project_name="parent")
        assert_shared(cli, base_share, base_project, "base-element.bst", project_name="base")

        # Ensure that, from now on, we ignore junction element remotes
        junction_data["config"] = {"ignore-junction-remotes": True}
        _yaml.roundtrip_dump(junction_data, junction_element)

        # Now delete everything from the local cache and try to
        # redownload from the shares.
        #
        cas = os.path.join(cli.directory, "cas")
        shutil.rmtree(cas)
        artifact_dir = os.path.join(cli.directory, "artifacts")
        shutil.rmtree(artifact_dir)

        # Assert that nothing is cached locally anymore
        state = cli.get_element_state(project, "target.bst")
        assert state != "cached"
        state = cli.get_element_state(base_project, "base-element.bst")
        assert state != "cached"

        # Now try bst artifact pull
        result = cli.run(project=project, args=["artifact", "pull", "--deps", "all", "target.bst"])
        assert result.exit_code == 0

        # And assert that they are again in the local cache, without having built
        state = cli.get_element_state(project, "target.bst")
        assert state == "cached"
        # We shouldn't be able to download base-element!
        state = cli.get_element_state(base_project, "base-element.bst")
        assert state != "cached"


@pytest.mark.datafiles(DATA_DIR)
def test_caching_elements_ignoring_remotes(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), "parent")
    base_project = os.path.join(str(project), "base")

    # Load the junction element
    junction_element = os.path.join(project, "base.bst")
    junction_data = _yaml.roundtrip_load(junction_element)

    # Configure to push everything to the project's remote and nothing to the junction's
    junction_data["config"] = {"cache-junction-elements": True, "ignore-junction-remotes": True}
    _yaml.roundtrip_dump(junction_data, junction_element)

    with create_artifact_share(os.path.join(str(tmpdir), "artifactshare-parent")) as share, create_artifact_share(
        os.path.join(str(tmpdir), "artifactshare-base")
    ) as base_share:

        # First build it without the artifact cache configured
        result = cli.run(project=project, args=["build", "target.bst"])
        assert result.exit_code == 0

        # Assert that we are now cached locally
        state = cli.get_element_state(project, "target.bst")
        assert state == "cached"
        state = cli.get_element_state(base_project, "base-element.bst")
        assert state == "cached"

        project_set_artifacts(project, share.repo)
        project_set_artifacts(base_project, base_share.repo)

        # Push to the remote(s))
        result = cli.run(project=project, args=["artifact", "push", "--deps", "all", "target.bst"])
        assert result.exit_code == 0

        # And finally assert that the artifacts are in the right shares
        #
        # The parent project's cache should *also* contain elements from the junction
        assert_shared(cli, share, project, "target.bst", project_name="parent")
        assert_shared(cli, share, project, "app.bst", project_name="parent")
        assert_shared(cli, share, base_project, "base-element.bst", project_name="base")

        # The junction project's cache should be empty
        assert_not_shared(cli, base_share, project, "target.bst", project_name="parent")
        assert_not_shared(cli, base_share, project, "app.bst", project_name="parent")
        assert_not_shared(cli, base_share, base_project, "base-element.bst", project_name="base")
