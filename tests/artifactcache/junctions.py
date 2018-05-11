import os
import shutil
import pytest
from tests.testutils import cli, create_artifact_share

from buildstream import _yaml


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "junctions",
)


# Assert that a given artifact is in the share
#
def assert_shared(cli, share, project_name, project, element_name):
    # NOTE: 'test' here is the name of the project
    # specified in the project.conf we are testing with.
    #
    cache_key = cli.get_element_key(project, element_name)
    if not share.has_artifact(project_name, element_name, cache_key):
        raise AssertionError("Artifact share at {} does not contain the expected element {}"
                             .format(share.repo, element_name))


def project_set_artifacts(project, url):
    project_conf_file = os.path.join(project, 'project.conf')
    project_config = _yaml.load(project_conf_file)
    project_config.update({
        'artifacts': {
            'url': url,
            'push': True
        }
    })
    _yaml.dump(_yaml.node_sanitize(project_config), filename=project_conf_file)


@pytest.mark.datafiles(DATA_DIR)
def test_push_pull(cli, tmpdir, datafiles):
    project = os.path.join(str(datafiles), 'foo')
    base_project = os.path.join(str(project), 'base')

    with create_artifact_share(os.path.join(str(tmpdir), 'artifactshare-foo')) as share,\
        create_artifact_share(os.path.join(str(tmpdir), 'artifactshare-base')) as base_share:

        # First build it without the artifact cache configured
        result = cli.run(project=project, args=['build', 'target.bst'])
        assert result.exit_code == 0

        # Assert that we are now cached locally
        state = cli.get_element_state(project, 'target.bst')
        assert state == 'cached'
        state = cli.get_element_state(base_project, 'target.bst')
        assert state == 'cached'

        project_set_artifacts(project, share.repo)
        project_set_artifacts(base_project, base_share.repo)

        # Now try bst push
        result = cli.run(project=project, args=['push', '--deps', 'all', 'target.bst'])
        assert result.exit_code == 0

        # And finally assert that the artifacts are in the right shares
        assert_shared(cli, share, 'foo', project, 'target.bst')
        assert_shared(cli, base_share, 'base', base_project, 'target.bst')

        # Now we've pushed, delete the user's local artifact cache
        # directory and try to redownload it from the share
        #
        artifacts = os.path.join(cli.directory, 'artifacts')
        shutil.rmtree(artifacts)

        # Assert that nothing is cached locally anymore
        state = cli.get_element_state(project, 'target.bst')
        assert state != 'cached'
        state = cli.get_element_state(base_project, 'target.bst')
        assert state != 'cached'

        # Now try bst pull
        result = cli.run(project=project, args=['pull', '--deps', 'all', 'target.bst'])
        assert result.exit_code == 0

        # And assert that they are again in the local cache, without having built
        state = cli.get_element_state(project, 'target.bst')
        assert state == 'cached'
        state = cli.get_element_state(base_project, 'target.bst')
        assert state == 'cached'
