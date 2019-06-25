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

from buildstream._context import Context
from buildstream._exceptions import ErrorDomain
from buildstream._project import Project
from buildstream import _yaml
from buildstream.testing import cli  # pylint: disable=unused-import
from buildstream.testing import create_repo

from tests.testutils import create_artifact_share

DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "project")


def message_handler(message, context):
    pass


@pytest.mark.datafiles(DATA_DIR)
def test_source_push(cli, tmpdir, datafiles):
    cache_dir = os.path.join(str(tmpdir), 'cache')
    project_dir = str(datafiles)

    with create_artifact_share(os.path.join(str(tmpdir), 'sourceshare')) as share:
        user_config_file = str(tmpdir.join('buildstream.conf'))
        user_config = {
            'scheduler': {
                'pushers': 1
            },
            'source-caches': {
                'url': share.repo,
                'push': True,
            },
            'cachedir': cache_dir,
        }
        _yaml.dump(user_config, filename=user_config_file)
        cli.configure(user_config)

        repo = create_repo('git', str(tmpdir))
        ref = repo.create(os.path.join(project_dir, 'files'))
        element_path = os.path.join(project_dir, 'elements')
        element_name = 'push.bst'
        element = {
            'kind': 'import',
            'sources': [repo.source_config(ref=ref)]
        }
        _yaml.dump(element, os.path.join(element_path, element_name))

        # get the source object
        context = Context()
        context.load(config=user_config_file)
        context.set_message_handler(message_handler)
        project = Project(project_dir, context)
        project.ensure_fully_loaded()

        element = project.load_elements(['push.bst'])[0]
        assert not element._source_cached()
        source = list(element.sources())[0]

        # check we don't have it in the current cache
        cas = context.get_cascache()
        assert not cas.contains(source._get_source_name())

        # build the element, this should fetch and then push the source to the
        # remote
        res = cli.run(project=project_dir, args=['build', 'push.bst'])
        res.assert_success()
        assert "Pushed source" in res.stderr

        # check that we've got the remote locally now
        sourcecache = context.sourcecache
        assert sourcecache.contains(source)

        # check that's the remote CAS now has it
        digest = share.cas.resolve_ref(source._get_source_name())
        assert share.has_object(digest)


@pytest.mark.datafiles(DATA_DIR)
def test_push_pull(cli, datafiles, tmpdir):
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
                'push': True,
            },
            'cachedir': cache_dir,
        }
        _yaml.dump(user_config, filename=user_config_file)
        cli.configure(user_config)

        # create repo to pull from
        repo = create_repo('git', str(tmpdir))
        ref = repo.create(os.path.join(project_dir, 'files'))
        element_path = os.path.join(project_dir, 'elements')
        element_name = 'push.bst'
        element = {
            'kind': 'import',
            'sources': [repo.source_config(ref=ref)]
        }
        _yaml.dump(element, os.path.join(element_path, element_name))

        res = cli.run(project=project_dir, args=['build', 'push.bst'])
        res.assert_success()

        # remove local cache dir, and repo files and check it all works
        shutil.rmtree(cache_dir)
        os.makedirs(cache_dir)
        shutil.rmtree(repo.repo)

        # check it's pulls from the share
        res = cli.run(project=project_dir, args=['build', 'push.bst'])
        res.assert_success()


@pytest.mark.datafiles(DATA_DIR)
def test_push_fail(cli, tmpdir, datafiles):
    project_dir = str(datafiles)
    cache_dir = os.path.join(str(tmpdir), 'cache')

    # set up config with remote that we'll take down
    with create_artifact_share(os.path.join(str(tmpdir), 'sourceshare')) as share:
        remote = share.repo
        user_config_file = str(tmpdir.join('buildstream.conf'))
        user_config = {
            'scheduler': {
                'pushers': 1
            },
            'source-caches': {
                'url': share.repo,
                'push': True,
            },
            'cachedir': cache_dir,
        }
        _yaml.dump(user_config, filename=user_config_file)
        cli.configure(user_config)

    # create repo to pull from
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project_dir, 'files'))
    element_path = os.path.join(project_dir, 'elements')
    element_name = 'push.bst'
    element = {
        'kind': 'import',
        'sources': [repo.source_config(ref=ref)]
    }
    _yaml.dump(element, os.path.join(element_path, element_name))

    # build and check that it fails to set up the remote
    res = cli.run(project=project_dir, args=['build', 'push.bst'])
    res.assert_success()

    assert "Failed to initialize remote {}".format(remote) in res.stderr
    assert "Pushing" not in res.stderr
    assert "Pushed" not in res.stderr


@pytest.mark.datafiles(DATA_DIR)
def test_source_push_build_fail(cli, tmpdir, datafiles):
    project_dir = str(datafiles)
    cache_dir = os.path.join(str(tmpdir), 'cache')

    with create_artifact_share(os.path.join(str(tmpdir), 'share')) as share:
        user_config = {
            'scheduler': {
                'pushers': 1
            },
            'source-caches': {
                'url': share.repo,
                'push': True,
            },
            'cachedir': cache_dir,
        }
        cli.configure(user_config)

        repo = create_repo('git', str(tmpdir))
        ref = repo.create(os.path.join(project_dir, 'files'))
        element_path = os.path.join(project_dir, 'elements')

        element_name = 'always-fail.bst'
        element = {
            'kind': 'always_fail',
            'sources': [repo.source_config(ref=ref)]
        }
        _yaml.dump(element, os.path.join(element_path, element_name))

        res = cli.run(project=project_dir, args=['build', 'always-fail.bst'])
        res.assert_main_error(ErrorDomain.STREAM, None)
        res.assert_task_error(ErrorDomain.ELEMENT, None)

        # Sources are not pushed as the build queue is before the source push
        # queue.
        assert "Pushed source " not in res.stderr
