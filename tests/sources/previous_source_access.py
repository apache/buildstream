# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream.testing import generate_project, load_yaml
from buildstream.testing import cli  # pylint: disable=unused-import

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "previous_source_access")


##################################################################
#                              Tests                             #
##################################################################
# Test that plugins can access data from previous sources
@pytest.mark.datafiles(DATA_DIR)
def test_custom_transform_source(cli, datafiles):
    project = str(datafiles)

    # Set the project_dir alias in project.conf to the path to the tested project
    project_config_path = os.path.join(project, "project.conf")
    project_config = load_yaml(project_config_path)
    aliases = project_config.get_mapping("aliases")
    aliases["project_dir"] = "file://{}".format(project)
    generate_project(project, project_config)

    # Ensure we can track
    result = cli.run(project=project, args=["source", "track", "target.bst"])
    result.assert_success()

    # Ensure we can fetch
    result = cli.run(project=project, args=["source", "fetch", "target.bst"])
    result.assert_success()

    # Ensure we get correct output from foo_transform
    cli.run(project=project, args=["build", "target.bst"])
    destpath = os.path.join(cli.directory, "checkout")
    result = cli.run(project=project, args=["artifact", "checkout", "target.bst", "--directory", destpath])
    result.assert_success()
    # Assert that files from both sources exist, and that they have
    # the same content
    assert os.path.exists(os.path.join(destpath, "file"))
    assert os.path.exists(os.path.join(destpath, "filetransform"))
    with open(os.path.join(destpath, "file")) as file1:
        with open(os.path.join(destpath, "filetransform")) as file2:
            assert file1.read() == file2.read()
