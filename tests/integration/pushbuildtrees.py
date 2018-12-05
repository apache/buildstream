import os
import shutil
import pytest
import subprocess

from buildstream import _yaml
from tests.testutils import create_artifact_share
from tests.testutils.site import HAVE_SANDBOX
from buildstream.plugintestutils import cli, cli_integration as cli2
from buildstream.plugintestutils.integration import assert_contains
from buildstream._exceptions import ErrorDomain, LoadErrorReason


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


# Remove artifact cache & set cli2.config value of pull-buildtrees
# to false, which is the default user context. The cache has to be
# cleared as just forcefully removing the refpath leaves dangling objects.
def default_state(cli2, tmpdir, share):
    shutil.rmtree(os.path.join(str(tmpdir), 'artifacts'))
    cli2.configure({
        'artifacts': {'url': share.repo, 'push': False},
        'artifactdir': os.path.join(str(tmpdir), 'artifacts'),
        'cache': {'pull-buildtrees': False},
    })


# Tests to capture the integration of the optionl push of buildtrees.
# The behaviour should encompass pushing artifacts that are already cached
# without a buildtree as well as artifacts that are cached with their buildtree.
# This option is handled via 'allow-partial-push' on a per artifact remote config
# node basis. Multiple remote config nodes can point to the same url and as such can
# have different 'allow-partial-push' options, tests need to cover this using project
# confs.
@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_pushbuildtrees(cli2, tmpdir, datafiles, integration_cache):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'autotools/amhello.bst'

    # Create artifact shares for pull & push testing
    with create_artifact_share(os.path.join(str(tmpdir), 'share1')) as share1,\
        create_artifact_share(os.path.join(str(tmpdir), 'share2')) as share2,\
        create_artifact_share(os.path.join(str(tmpdir), 'share3')) as share3,\
        create_artifact_share(os.path.join(str(tmpdir), 'share4')) as share4:

        cli2.configure({
            'artifacts': {'url': share1.repo, 'push': True},
            'artifactdir': os.path.join(str(tmpdir), 'artifacts')
        })

        cli2.configure({'artifacts': [{'url': share1.repo, 'push': True},
                                     {'url': share2.repo, 'push': True, 'allow-partial-push': True}]})

        # Build autotools element, checked pushed, delete local.
        # As share 2 has push & allow-partial-push set a true, it
        # should have pushed the artifacts, without the cached buildtrees,
        # to it.
        result = cli2.run(project=project, args=['build', element_name])
        assert result.exit_code == 0
        assert cli2.get_element_state(project, element_name) == 'cached'
        elementdigest = share1.has_artifact('test', element_name, cli2.get_element_key(project, element_name))
        buildtreedir = os.path.join(str(tmpdir), 'artifacts', 'extract', 'test', 'autotools-amhello',
                                    elementdigest.hash, 'buildtree')
        assert os.path.isdir(buildtreedir)
        assert element_name in result.get_partial_pushed_elements()
        assert element_name in result.get_pushed_elements()
        assert share1.has_artifact('test', element_name, cli2.get_element_key(project, element_name))
        assert share2.has_artifact('test', element_name, cli2.get_element_key(project, element_name))
        default_state(cli2, tmpdir, share1)

        # Check that after explictly pulling an artifact without it's buildtree,
        # we can push it to another remote that is configured to accept the partial
        # artifact
        result = cli2.run(project=project, args=['artifact', 'pull', element_name])
        assert element_name in result.get_pulled_elements()
        cli2.configure({'artifacts': {'url': share3.repo, 'push': True, 'allow-partial-push': True}})
        assert cli2.get_element_state(project, element_name) == 'cached'
        assert not os.path.isdir(buildtreedir)
        result = cli2.run(project=project, args=['artifact', 'push', element_name])
        assert result.exit_code == 0
        assert element_name in result.get_partial_pushed_elements()
        assert element_name not in result.get_pushed_elements()
        assert share3.has_artifact('test', element_name, cli2.get_element_key(project, element_name))
        default_state(cli2, tmpdir, share3)

        # Delete the local cache and pull the partial artifact from share 3,
        # this should not include the buildtree when extracted locally, even when
        # pull-buildtrees is given as a cli2 parameter as no available remotes will
        # contain the buildtree
        assert not os.path.isdir(buildtreedir)
        assert cli2.get_element_state(project, element_name) != 'cached'
        result = cli2.run(project=project, args=['--pull-buildtrees', 'artifact', 'pull', element_name])
        assert element_name in result.get_partial_pulled_elements()
        assert not os.path.isdir(buildtreedir)
        default_state(cli2, tmpdir, share3)

        # Delete the local cache and attempt to pull a 'full' artifact, including its
        # buildtree. As with before share3 being the first listed remote will not have
        # the buildtree available and should spawn a partial pull. Having share1 as the
        # second available remote should allow the buildtree to be pulled thus 'completing'
        # the artifact
        cli2.configure({'artifacts': [{'url': share3.repo, 'push': True, 'allow-partial-push': True},
                                     {'url': share1.repo, 'push': True}]})
        assert cli2.get_element_state(project, element_name) != 'cached'
        result = cli2.run(project=project, args=['--pull-buildtrees', 'artifact', 'pull', element_name])
        assert element_name in result.get_partial_pulled_elements()
        assert element_name in result.get_pulled_elements()
        assert "Attempting to retrieve buildtree from remotes" in result.stderr
        assert os.path.isdir(buildtreedir)
        assert cli2.get_element_state(project, element_name) == 'cached'

        # Test that we are able to 'complete' an artifact on a server which is cached partially,
        # but has now been configured for full artifact pushing. This should require only pushing
        # the missing blobs, which should be those of just the buildtree. In this case changing
        # share3 to full pushes should exercise this
        cli2.configure({'artifacts': {'url': share3.repo, 'push': True}})
        result = cli2.run(project=project, args=['artifact', 'push', element_name])
        assert element_name in result.get_pushed_elements()

        # Ensure that the same remote url can be defined multiple times with differing push
        # config. Buildstream supports the same remote having different configurations which
        # partial pushing could be different for elements defined at a top level project.conf to
        # those from a junctioned project. Assert that elements are pushed to the same remote in
        # a state defined via their respective project.confs
        default_state(cli2, tmpdir, share1)
        cli2.configure({'artifactdir': os.path.join(str(tmpdir), 'artifacts')}, reset=True)
        junction = os.path.join(project, 'elements', 'junction')
        os.mkdir(junction)
        shutil.copy2(os.path.join(project, 'elements', element_name), junction)

        junction_conf = {}
        project_conf = {}
        junction_conf['name'] = 'amhello'
        junction_conf['artifacts'] = {'url': share4.repo, 'push': True, 'allow-partial-push': True}
        _yaml.dump(junction_conf, os.path.join(junction, 'project.conf'))
        project_conf['artifacts'] = {'url': share4.repo, 'push': True}

        # Read project.conf, the junction project.conf and buildstream.conf
        # before running bst
        with open(os.path.join(project, 'project.conf'), 'r') as f:
            print(f.read())
        with open(os.path.join(junction, 'project.conf'), 'r') as f:
            print(f.read())
        with open(os.path.join(project, 'cache', 'buildstream.conf'), 'r') as f:
            print(f.read())

        result = cli2.run(project=project, args=['build', 'junction/amhello.bst'], project_config=project_conf)

        # Read project.conf, the junction project.conf and buildstream.conf
        # after running bst
        with open(os.path.join(project, 'project.conf'), 'r') as f:
            print(f.read())
        with open(os.path.join(junction, 'project.conf'), 'r') as f:
            print(f.read())
        with open(os.path.join(project, 'cache', 'buildstream.conf'), 'r') as f:
            print(f.read())

        assert 'junction/amhello.bst' in result.get_partial_pushed_elements()
        assert 'base/base-alpine.bst' in result.get_pushed_elements()
