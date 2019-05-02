import os
import pytest

from buildstream import _yaml
from tests.testutils import cli

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'previous_source_access'
)


##################################################################
#                              Tests                             #
##################################################################
# Test that plugins can access data from previous sources
@pytest.mark.datafiles(DATA_DIR)
def test_custom_transform_source(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Set the project_dir alias in project.conf to the path to the tested project
    project_config_path = os.path.join(project, "project.conf")
    project_config = _yaml.load(project_config_path)
    aliases = _yaml.node_get(project_config, dict, "aliases")
    aliases["project_dir"] = "file://{}".format(project)
    _yaml.dump(_yaml.node_sanitize(project_config), project_config_path)

    # Ensure we can track
    result = cli.run(project=project, args=[
        'track', 'target.bst'
    ])
    result.assert_success()

    # Ensure we can fetch
    result = cli.run(project=project, args=[
        'fetch', 'target.bst'
    ])
    result.assert_success()

    # Ensure we get correct output from foo_transform
    result = cli.run(project=project, args=[
        'build', 'target.bst'
    ])
    destpath = os.path.join(cli.directory, 'checkout')
    result = cli.run(project=project, args=[
        'checkout', 'target.bst', destpath
    ])
    result.assert_success()
    # Assert that files from both sources exist, and that they have
    # the same content
    assert os.path.exists(os.path.join(destpath, 'file'))
    assert os.path.exists(os.path.join(destpath, 'filetransform'))
    with open(os.path.join(destpath, 'file')) as file1:
        with open(os.path.join(destpath, 'filetransform')) as file2:
            assert file1.read() == file2.read()
