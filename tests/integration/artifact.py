#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2018 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors: Richard Maw <richard.maw@codethink.co.uk>
#

from contextlib import contextmanager
import os
import pytest
import shutil
import tempfile

from buildstream import utils
from buildstream.plugintestutils import cli_integration as cli
from tests.testutils import create_artifact_share
from tests.testutils.site import HAVE_SANDBOX
from buildstream._cas import CASCache

pytestmark = pytest.mark.integration


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


# A test to capture the integration of the cachebuildtrees
# behaviour, which by default is to include the buildtree
# content of an element on caching.
@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.skipif(not HAVE_SANDBOX, reason='Only available with a functioning sandbox')
def test_cache_buildtrees(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'autotools/amhello.bst'

    # Create artifact shares for pull & push testing
    with create_artifact_share(os.path.join(str(tmpdir), 'share1')) as share1,\
        create_artifact_share(os.path.join(str(tmpdir), 'share2')) as share2,\
        create_artifact_share(os.path.join(str(tmpdir), 'share3')) as share3:
        cli.configure({
            'artifacts': {'url': share1.repo, 'push': True},
            'cachedir': str(tmpdir)
        })

        @contextmanager
        def cas_extract_buildtree(digest):
            extractdir = tempfile.mkdtemp(prefix="tmp", dir=str(tmpdir))
            try:
                cas = CASCache(str(tmpdir))
                cas.checkout(extractdir, digest)
                yield os.path.join(extractdir, 'buildtree')
            finally:
                utils._force_rmtree(extractdir)

        # Build autotools element with cache-buildtrees set via the
        # cli. The artifact should be successfully pushed to the share1 remote
        # and cached locally with an 'empty' buildtree digest, as it's not a
        # dangling ref
        result = cli.run(project=project, args=['--cache-buildtrees', 'never', 'build', element_name])
        assert result.exit_code == 0
        assert cli.get_element_state(project, element_name) == 'cached'
        assert share1.has_artifact('test', element_name, cli.get_element_key(project, element_name))

        # The extracted buildtree dir should be empty, as we set the config
        # to not cache buildtrees
        cache_key = cli.get_element_key(project, element_name)
        elementdigest = share1.has_artifact('test', element_name, cache_key)
        with cas_extract_buildtree(elementdigest) as buildtreedir:
            assert os.path.isdir(buildtreedir)
            assert not os.listdir(buildtreedir)

        # Delete the local cached artifacts, and assert the when pulled with --pull-buildtrees
        # that is was cached in share1 as expected with an empty buildtree dir
        shutil.rmtree(os.path.join(str(tmpdir), 'cas'))
        assert cli.get_element_state(project, element_name) != 'cached'
        result = cli.run(project=project, args=['--pull-buildtrees', 'artifact', 'pull', element_name])
        assert element_name in result.get_pulled_elements()
        with cas_extract_buildtree(elementdigest) as buildtreedir:
            assert os.path.isdir(buildtreedir)
            assert not os.listdir(buildtreedir)
        shutil.rmtree(os.path.join(str(tmpdir), 'cas'))

        # Assert that the default behaviour of pull to not include buildtrees on the artifact
        # in share1 which was purposely cached with an empty one behaves as expected. As such the
        # pulled artifact will have a dangling ref for the buildtree dir, regardless of content,
        # leading to no buildtreedir being extracted
        result = cli.run(project=project, args=['artifact', 'pull', element_name])
        assert element_name in result.get_pulled_elements()
        with cas_extract_buildtree(elementdigest) as buildtreedir:
            assert not os.path.isdir(buildtreedir)
        shutil.rmtree(os.path.join(str(tmpdir), 'cas'))

        # Repeat building the artifacts, this time with the default behaviour of caching buildtrees,
        # as such the buildtree dir should not be empty
        cli.configure({
            'artifacts': {'url': share2.repo, 'push': True},
            'cachedir': str(tmpdir)
        })
        result = cli.run(project=project, args=['build', element_name])
        assert result.exit_code == 0
        assert cli.get_element_state(project, element_name) == 'cached'
        assert share2.has_artifact('test', element_name, cli.get_element_key(project, element_name))

        # Cache key will be the same however the digest hash will have changed as expected, so reconstruct paths
        elementdigest = share2.has_artifact('test', element_name, cache_key)
        with cas_extract_buildtree(elementdigest) as buildtreedir:
            assert os.path.isdir(buildtreedir)
            assert os.listdir(buildtreedir) is not None

        # Delete the local cached artifacts, and assert that when pulled with --pull-buildtrees
        # that it was cached in share2 as expected with a populated buildtree dir
        shutil.rmtree(os.path.join(str(tmpdir), 'cas'))
        assert cli.get_element_state(project, element_name) != 'cached'
        result = cli.run(project=project, args=['--pull-buildtrees', 'artifact', 'pull', element_name])
        assert element_name in result.get_pulled_elements()
        with cas_extract_buildtree(elementdigest) as buildtreedir:
            assert os.path.isdir(buildtreedir)
            assert os.listdir(buildtreedir) is not None
        shutil.rmtree(os.path.join(str(tmpdir), 'cas'))

        # Clarify that the user config option for cache-buildtrees works as the cli
        # main option does. Point to share3 which does not have the artifacts cached to force
        # a build
        cli.configure({
            'artifacts': {'url': share3.repo, 'push': True},
            'cachedir': str(tmpdir),
            'cache': {'cache-buildtrees': 'never'}
        })
        result = cli.run(project=project, args=['build', element_name])
        assert result.exit_code == 0
        assert cli.get_element_state(project, element_name) == 'cached'
        cache_key = cli.get_element_key(project, element_name)
        elementdigest = share3.has_artifact('test', element_name, cache_key)
        with cas_extract_buildtree(elementdigest) as buildtreedir:
            assert os.path.isdir(buildtreedir)
            assert not os.listdir(buildtreedir)
