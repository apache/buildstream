#
#  Copyright (C) 2019 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.	 See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
#  Authors:
#        Raoul Hidalgo Charman <raoul.hidalgocharman@codethink.co.uk>
#
# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name
import os
import shutil
import pytest

from buildstream._exceptions import ErrorDomain
from buildstream._context import Context
from buildstream._project import Project
from buildstream import _yaml
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.testing import create_repo
from tests.testutils import create_artifact_share

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


def message_handler(message, context):
    pass


@pytest.mark.datafiles(DATA_DIR)
def test_source_fetch(cli, tmpdir, datafiles):
    project_dir = str(datafiles)

    # use artifact cache for sources for now, they should work the same
    with create_artifact_share(os.path.join(str(tmpdir), 'sourceshare')) as share:
        # configure using this share
        cache_dir = os.path.join(str(tmpdir), 'cache')
        user_config_file = str(tmpdir.join('buildstream.conf'))
        user_config = {
            'scheduler': {
                'pushers': 1
            },
            'source-caches': {
                'url': share.repo,
            },
            'cachedir': cache_dir,
        }
        _yaml.roundtrip_dump(user_config, file=user_config_file)
        cli.configure(user_config)

        repo = create_repo('git', str(tmpdir))
        ref = repo.create(os.path.join(project_dir, 'files'))
        element_path = os.path.join(project_dir, 'elements')
        element_name = 'fetch.bst'
        element = {
            'kind': 'import',
            'sources': [repo.source_config(ref=ref)]
        }
        _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

        context = Context()
        context.load(config=user_config_file)
        context.set_message_handler(message_handler)

        project = Project(project_dir, context)
        project.ensure_fully_loaded()

        element = project.load_elements(['fetch.bst'])[0]
        assert not element._source_cached()
        source = list(element.sources())[0]

        cas = context.get_cascache()
        assert not cas.contains(source._get_source_name())

        # Just check that we sensibly fetch and build the element
        res = cli.run(project=project_dir, args=['build', 'fetch.bst'])
        res.assert_success()

        assert os.listdir(os.path.join(str(tmpdir), 'cache', 'sources', 'git')) != []

        # Move source in local cas to repo
        shutil.rmtree(os.path.join(str(tmpdir), 'sourceshare', 'repo', 'cas'))
        shutil.move(
            os.path.join(str(tmpdir), 'cache', 'cas'),
            os.path.join(str(tmpdir), 'sourceshare', 'repo'))
        shutil.rmtree(os.path.join(str(tmpdir), 'cache', 'sources'))
        shutil.rmtree(os.path.join(str(tmpdir), 'cache', 'artifacts'))

        digest = share.cas.resolve_ref(source._get_source_name())
        assert share.has_object(digest)

        state = cli.get_element_state(project_dir, 'fetch.bst')
        assert state == 'fetch needed'

        # Now fetch the source and check
        res = cli.run(project=project_dir, args=['source', 'fetch', 'fetch.bst'])
        res.assert_success()
        assert "Pulled source" in res.stderr

        # check that we have the source in the cas now and it's not fetched
        assert element._source_cached()
        assert os.listdir(os.path.join(str(tmpdir), 'cache', 'sources', 'git')) == []


@pytest.mark.datafiles(DATA_DIR)
def test_fetch_fallback(cli, tmpdir, datafiles):
    project_dir = str(datafiles)

    # use artifact cache for sources for now, they should work the same
    with create_artifact_share(os.path.join(str(tmpdir), 'sourceshare')) as share:
        # configure using this share
        cache_dir = os.path.join(str(tmpdir), 'cache')
        user_config_file = str(tmpdir.join('buildstream.conf'))
        user_config = {
            'scheduler': {
                'pushers': 1
            },
            'source-caches': {
                'url': share.repo,
            },
            'cachedir': cache_dir,
        }
        _yaml.roundtrip_dump(user_config, file=user_config_file)
        cli.configure(user_config)

        repo = create_repo('git', str(tmpdir))
        ref = repo.create(os.path.join(project_dir, 'files'))
        element_path = os.path.join(project_dir, 'elements')
        element_name = 'fetch.bst'
        element = {
            'kind': 'import',
            'sources': [repo.source_config(ref=ref)]
        }
        _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

        context = Context()
        context.load(config=user_config_file)
        context.set_message_handler(message_handler)

        project = Project(project_dir, context)
        project.ensure_fully_loaded()

        element = project.load_elements(['fetch.bst'])[0]
        assert not element._source_cached()
        source = list(element.sources())[0]

        cas = context.get_cascache()
        assert not cas.contains(source._get_source_name())
        assert not os.path.exists(os.path.join(cache_dir, 'sources'))

        # Now check if it falls back to the source fetch method.
        res = cli.run(project=project_dir, args=['source', 'fetch', 'fetch.bst'])
        res.assert_success()
        brief_key = source._get_brief_display_key()
        assert ("Remote ({}) does not have source {} cached"
                .format(share.repo, brief_key)) in res.stderr
        assert ("SUCCESS Fetching from {}"
                .format(repo.source_config(ref=ref)['url'])) in res.stderr

        # Check that the source in both in the source dir and the local CAS
        assert element._source_cached()


@pytest.mark.datafiles(DATA_DIR)
def test_pull_fail(cli, tmpdir, datafiles):
    project_dir = str(datafiles)
    cache_dir = os.path.join(str(tmpdir), 'cache')

    with create_artifact_share(os.path.join(str(tmpdir), 'sourceshare')) as share:
        user_config_file = str(tmpdir.join('buildstream.conf'))
        user_config = {
            'scheduler': {
                'pushers': 1
            },
            'source-caches': {
                'url': share.repo,
            },
            'cachedir': cache_dir,
        }
        _yaml.roundtrip_dump(user_config, file=user_config_file)
        cli.configure(user_config)

        repo = create_repo('git', str(tmpdir))
        ref = repo.create(os.path.join(project_dir, 'files'))
        element_path = os.path.join(project_dir, 'elements')
        element_name = 'push.bst'
        element = {
            'kind': 'import',
            'sources': [repo.source_config(ref=ref)]
        }
        _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

        # get the source object
        context = Context()
        context.load(config=user_config_file)
        context.set_message_handler(message_handler)
        project = Project(project_dir, context)
        project.ensure_fully_loaded()

        element = project.load_elements(['push.bst'])[0]
        assert not element._source_cached()
        source = list(element.sources())[0]

        # remove files and check that it doesn't build
        shutil.rmtree(repo.repo)

        # Should fail in stream, with a plugin tasks causing the error
        res = cli.run(project=project_dir, args=['build', 'push.bst'])
        res.assert_main_error(ErrorDomain.STREAM, None)
        res.assert_task_error(ErrorDomain.PLUGIN, None)
        assert "Remote ({}) does not have source {} cached".format(
            share.repo, source._get_brief_display_key()) in res.stderr
