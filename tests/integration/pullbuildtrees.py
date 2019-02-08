import os
import shutil
import pytest

from tests.testutils import create_artifact_share
from tests.testutils.site import HAVE_SANDBOX

from buildstream.plugintestutils.integration import assert_contains
from buildstream.plugintestutils import cli, cli_integration as cli2
from buildstream.plugintestutils.integration import assert_contains
from buildstream._exceptions import ErrorDomain, LoadErrorReason


DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project"
)


# Remove artifact cache & set cli.config value of pull-buildtrees
# to false, which is the default user context. The cache has to be
# cleared as just forcefully removing the refpath leaves dangling objects.
def default_state(cli, tmpdir, share):
    shutil.rmtree(os.path.join(str(tmpdir), 'artifacts'))
    cli.configure({
        'artifacts': {'url': share.repo, 'push': False},
        'artifactdir': os.path.join(str(tmpdir), 'artifacts'),
        'cache': {'pull-buildtrees': False},
    })


# A test to capture the integration of the pullbuildtrees
# behaviour, which by default is to not include the buildtree
# directory of an element.
@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_pullbuildtrees(cli2, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'autotools/amhello.bst'

    # Create artifact shares for pull & push testing
    with create_artifact_share(os.path.join(str(tmpdir), 'share1')) as share1,\
        create_artifact_share(os.path.join(str(tmpdir), 'share2')) as share2,\
        create_artifact_share(os.path.join(str(tmpdir), 'share3')) as share3:
        cli2.configure({
            'artifacts': {'url': share1.repo, 'push': True},
            'artifactdir': os.path.join(str(tmpdir), 'artifacts')
        })

        # Build autotools element, checked pushed, delete local
        result = cli2.run(project=project, args=['build', element_name])
        assert result.exit_code == 0
        assert cli2.get_element_state(project, element_name) == 'cached'
        assert share1.has_artifact('test', element_name, cli2.get_element_key(project, element_name))
        default_state(cli2, tmpdir, share1)

        # Pull artifact with default config, assert that pulling again
        # doesn't create a pull job, then assert with buildtrees user
        # config set creates a pull job.
        result = cli2.run(project=project, args=['artifact', 'pull', element_name])
        assert element_name in result.get_pulled_elements()
        result = cli2.run(project=project, args=['artifact', 'pull', element_name])
        assert element_name not in result.get_pulled_elements()
        cli2.configure({'cache': {'pull-buildtrees': True}})
        result = cli2.run(project=project, args=['artifact', 'pull', element_name])
        assert element_name in result.get_pulled_elements()
        default_state(cli2, tmpdir, share1)

        # Pull artifact with default config, then assert that pulling
        # with buildtrees cli flag set creates a pull job.
        # Also assert that the buildtree is added to the artifact's
        # extract dir
        result = cli2.run(project=project, args=['artifact', 'pull', element_name])
        assert element_name in result.get_pulled_elements()
        elementdigest = share1.has_artifact('test', element_name, cli2.get_element_key(project, element_name))
        buildtreedir = os.path.join(str(tmpdir), 'artifacts', 'extract', 'test', 'autotools-amhello',
                                    elementdigest.hash, 'buildtree')
        assert not os.path.isdir(buildtreedir)
        result = cli2.run(project=project, args=['--pull-buildtrees', 'artifact', 'pull', element_name])
        assert element_name in result.get_pulled_elements()
        assert os.path.isdir(buildtreedir)
        default_state(cli2, tmpdir, share1)

        # Pull artifact with pullbuildtrees set in user config, then assert
        # that pulling with the same user config doesn't creates a pull job,
        # or when buildtrees cli flag is set.
        cli2.configure({'cache': {'pull-buildtrees': True}})
        result = cli2.run(project=project, args=['artifact', 'pull', element_name])
        assert element_name in result.get_pulled_elements()
        result = cli2.run(project=project, args=['artifact', 'pull', element_name])
        assert element_name not in result.get_pulled_elements()
        result = cli2.run(project=project, args=['--pull-buildtrees', 'artifact', 'pull', element_name])
        assert element_name not in result.get_pulled_elements()
        default_state(cli2, tmpdir, share1)

        # Pull artifact with default config and buildtrees cli flag set, then assert
        # that pulling with pullbuildtrees set in user config doesn't create a pull
        # job.
        result = cli2.run(project=project, args=['--pull-buildtrees', 'artifact', 'pull', element_name])
        assert element_name in result.get_pulled_elements()
        cli2.configure({'cache': {'pull-buildtrees': True}})
        result = cli2.run(project=project, args=['artifact', 'pull', element_name])
        assert element_name not in result.get_pulled_elements()
        default_state(cli2, tmpdir, share1)

        # Assert that a partial build element (not containing a populated buildtree dir)
        # can't be pushed to an artifact share, then assert that a complete build element
        # can be. This will attempt a partial pull from share1 and then a partial push
        # to share2
        result = cli2.run(project=project, args=['artifact', 'pull', element_name])
        assert element_name in result.get_pulled_elements()
        cli2.configure({'artifacts': {'url': share2.repo, 'push': True}})
        result = cli2.run(project=project, args=['artifact', 'push', element_name])
        assert element_name not in result.get_pushed_elements()
        assert not share2.has_artifact('test', element_name, cli2.get_element_key(project, element_name))

        # Assert that after pulling the missing buildtree the element artifact can be
        # successfully pushed to the remote. This will attempt to pull the buildtree
        # from share1 and then a 'complete' push to share2
        cli2.configure({'artifacts': {'url': share1.repo, 'push': False}})
        result = cli2.run(project=project, args=['--pull-buildtrees', 'artifact', 'pull', element_name])
        assert element_name in result.get_pulled_elements()
        cli2.configure({'artifacts': {'url': share2.repo, 'push': True}})
        result = cli2.run(project=project, args=['artifact', 'push', element_name])
        assert element_name in result.get_pushed_elements()
        assert share2.has_artifact('test', element_name, cli2.get_element_key(project, element_name))
        default_state(cli2, tmpdir, share1)

        # Assert that bst push will automatically attempt to pull a missing buildtree
        # if pull-buildtrees is set, however as share3 is the only defined remote and is empty,
        # assert that no element artifact buildtrees are pulled (no available remote buildtree) and thus the
        # artifact cannot be pushed.
        result = cli2.run(project=project, args=['artifact', 'pull', element_name])
        assert element_name in result.get_pulled_elements()
        cli2.configure({'artifacts': {'url': share3.repo, 'push': True}})
        result = cli2.run(project=project, args=['--pull-buildtrees', 'artifact', 'push', element_name])
        assert "Attempting to fetch missing artifact buildtrees" in result.stderr
        assert element_name not in result.get_pulled_elements()
        assert not os.path.isdir(buildtreedir)
        assert element_name not in result.get_pushed_elements()
        assert not share3.has_artifact('test', element_name, cli2.get_element_key(project, element_name))

        # Assert that if we add an extra remote that has the buildtree artfact cached, bst push will
        # automatically attempt to pull it and will be successful, leading to the full artifact being pushed
        # to the empty share3. This gives the ability to attempt push currently partial artifacts to a remote,
        # without exlipictly requiring a bst pull.
        cli2.configure({'artifacts': [{'url': share1.repo, 'push': False}, {'url': share3.repo, 'push': True}]})
        result = cli2.run(project=project, args=['--pull-buildtrees', 'artifact', 'push', element_name])
        assert "Attempting to fetch missing artifact buildtrees" in result.stderr
        assert element_name in result.get_pulled_elements()
        assert os.path.isdir(buildtreedir)
        assert element_name in result.get_pushed_elements()
        assert share3.has_artifact('test', element_name, cli2.get_element_key(project, element_name))


# Ensure that only valid pull-buildtrees boolean options make it through the loading
# process.
@pytest.mark.parametrize("value,success", [
    (True, True),
    (False, True),
    ("pony", False),
    ("1", False)
])
@pytest.mark.datafiles(DATA_DIR)
def test_invalid_cache_pullbuildtrees(cli, datafiles, tmpdir, value, success):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    cli.configure({
        'cache': {
            'pull-buildtrees': value,
        }
    })

    res = cli.run(project=project, args=['workspace', 'list'])
    if success:
        res.assert_success()
    else:
        res.assert_main_error(ErrorDomain.LOAD, LoadErrorReason.ILLEGAL_COMPOSITE)
