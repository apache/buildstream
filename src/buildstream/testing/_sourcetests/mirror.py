#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2019 Bloomberg Finance LP
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

# Pylint doesn't play well with fixtures and dependency injection from pytest
# pylint: disable=redefined-outer-name

import os
import pytest

from buildstream import _yaml
from buildstream._exceptions import ErrorDomain
from .._utils import generate_junction
from .. import create_repo, ALL_REPO_KINDS
from .. import cli  # pylint: disable=unused-import

# Project directory
TOP_DIR = os.path.dirname(os.path.realpath(__file__))
DATA_DIR = os.path.join(TOP_DIR, 'project')


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_mirror_fetch(cli, tmpdir, datafiles, kind):
    bin_files_path = os.path.join(str(datafiles), 'files', 'bin-files', 'usr')
    dev_files_path = os.path.join(str(datafiles), 'files', 'dev-files', 'usr')
    upstream_repodir = os.path.join(str(tmpdir), 'upstream')
    mirror_repodir = os.path.join(str(tmpdir), 'mirror')
    project_dir = os.path.join(str(tmpdir), 'project')
    os.makedirs(project_dir)
    element_dir = os.path.join(project_dir, 'elements')

    # Create repo objects of the upstream and mirror
    upstream_repo = create_repo(kind, upstream_repodir)
    upstream_repo.create(bin_files_path)
    mirror_repo = upstream_repo.copy(mirror_repodir)
    upstream_ref = upstream_repo.create(dev_files_path)

    element = {
        'kind': 'import',
        'sources': [
            upstream_repo.source_config(ref=upstream_ref)
        ]
    }
    element_name = 'test.bst'
    element_path = os.path.join(element_dir, element_name)
    full_repo = element['sources'][0]['url']
    upstream_map, repo_name = os.path.split(full_repo)
    alias = 'foo-' + kind
    aliased_repo = alias + ':' + repo_name
    element['sources'][0]['url'] = aliased_repo
    full_mirror = mirror_repo.source_config()['url']
    mirror_map, _ = os.path.split(full_mirror)
    os.makedirs(element_dir)
    _yaml.dump(element, element_path)

    project = {
        'name': 'test',
        'element-path': 'elements',
        'aliases': {
            alias: upstream_map + "/"
        },
        'mirrors': [
            {
                'name': 'middle-earth',
                'aliases': {
                    alias: [mirror_map + "/"],
                },
            },
        ]
    }
    project_file = os.path.join(project_dir, 'project.conf')
    _yaml.dump(project, project_file)

    # No obvious ways of checking that the mirror has been fetched
    # But at least we can be sure it succeeds
    result = cli.run(project=project_dir, args=['source', 'fetch', element_name])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_mirror_fetch_upstream_absent(cli, tmpdir, datafiles, kind):
    dev_files_path = os.path.join(str(datafiles), 'files', 'dev-files', 'usr')
    upstream_repodir = os.path.join(str(tmpdir), 'upstream')
    mirror_repodir = os.path.join(str(tmpdir), 'mirror')
    project_dir = os.path.join(str(tmpdir), 'project')
    os.makedirs(project_dir)
    element_dir = os.path.join(project_dir, 'elements')

    # Create repo objects of the upstream and mirror
    upstream_repo = create_repo(kind, upstream_repodir)
    ref = upstream_repo.create(dev_files_path)
    mirror_repo = upstream_repo.copy(mirror_repodir)

    element = {
        'kind': 'import',
        'sources': [
            upstream_repo.source_config(ref=ref)
        ]
    }

    element_name = 'test.bst'
    element_path = os.path.join(element_dir, element_name)
    full_repo = element['sources'][0]['url']
    _, repo_name = os.path.split(full_repo)
    alias = 'foo-' + kind
    aliased_repo = alias + ':' + repo_name
    element['sources'][0]['url'] = aliased_repo
    full_mirror = mirror_repo.source_config()['url']
    mirror_map, _ = os.path.split(full_mirror)
    os.makedirs(element_dir)
    _yaml.dump(element, element_path)

    project = {
        'name': 'test',
        'element-path': 'elements',
        'aliases': {
            alias: 'http://www.example.com/'
        },
        'mirrors': [
            {
                'name': 'middle-earth',
                'aliases': {
                    alias: [mirror_map + "/"],
                },
            },
        ]
    }
    project_file = os.path.join(project_dir, 'project.conf')
    _yaml.dump(project, project_file)

    result = cli.run(project=project_dir, args=['source', 'fetch', element_name])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_mirror_from_includes(cli, tmpdir, datafiles, kind):
    bin_files_path = os.path.join(str(datafiles), 'files', 'bin-files', 'usr')
    upstream_repodir = os.path.join(str(tmpdir), 'upstream')
    mirror_repodir = os.path.join(str(tmpdir), 'mirror')
    project_dir = os.path.join(str(tmpdir), 'project')
    os.makedirs(project_dir)
    element_dir = os.path.join(project_dir, 'elements')

    # Create repo objects of the upstream and mirror
    upstream_repo = create_repo(kind, upstream_repodir)
    upstream_ref = upstream_repo.create(bin_files_path)
    mirror_repo = upstream_repo.copy(mirror_repodir)

    element = {
        'kind': 'import',
        'sources': [
            upstream_repo.source_config(ref=upstream_ref)
        ]
    }
    element_name = 'test.bst'
    element_path = os.path.join(element_dir, element_name)
    full_repo = element['sources'][0]['url']
    upstream_map, repo_name = os.path.split(full_repo)
    alias = 'foo-' + kind
    aliased_repo = alias + ':' + repo_name
    element['sources'][0]['url'] = aliased_repo
    full_mirror = mirror_repo.source_config()['url']
    mirror_map, _ = os.path.split(full_mirror)
    os.makedirs(element_dir)
    _yaml.dump(element, element_path)

    config_project_dir = str(tmpdir.join('config'))
    os.makedirs(config_project_dir, exist_ok=True)
    config_project = {
        'name': 'config'
    }
    _yaml.dump(config_project, os.path.join(config_project_dir, 'project.conf'))
    extra_mirrors = {
        'mirrors': [
            {
                'name': 'middle-earth',
                'aliases': {
                    alias: [mirror_map + "/"],
                }
            }
        ]
    }
    _yaml.dump(extra_mirrors, os.path.join(config_project_dir, 'mirrors.yml'))
    generate_junction(str(tmpdir.join('config_repo')),
                      config_project_dir,
                      os.path.join(element_dir, 'config.bst'))

    project = {
        'name': 'test',
        'element-path': 'elements',
        'aliases': {
            alias: upstream_map + "/"
        },
        '(@)': [
            'config.bst:mirrors.yml'
        ]
    }
    project_file = os.path.join(project_dir, 'project.conf')
    _yaml.dump(project, project_file)

    # Now make the upstream unavailable.
    os.rename(upstream_repo.repo, '{}.bak'.format(upstream_repo.repo))
    result = cli.run(project=project_dir, args=['source', 'fetch', element_name])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_mirror_junction_from_includes(cli, tmpdir, datafiles, kind):
    bin_files_path = os.path.join(str(datafiles), 'files', 'bin-files', 'usr')
    upstream_repodir = os.path.join(str(tmpdir), 'upstream')
    mirror_repodir = os.path.join(str(tmpdir), 'mirror')
    project_dir = os.path.join(str(tmpdir), 'project')
    os.makedirs(project_dir)
    element_dir = os.path.join(project_dir, 'elements')

    # Create repo objects of the upstream and mirror
    upstream_repo = create_repo(kind, upstream_repodir)
    upstream_ref = upstream_repo.create(bin_files_path)
    mirror_repo = upstream_repo.copy(mirror_repodir)

    element = {
        'kind': 'junction',
        'sources': [
            upstream_repo.source_config(ref=upstream_ref)
        ]
    }
    element_name = 'test.bst'
    element_path = os.path.join(element_dir, element_name)
    full_repo = element['sources'][0]['url']
    upstream_map, repo_name = os.path.split(full_repo)
    alias = 'foo-' + kind
    aliased_repo = alias + ':' + repo_name
    element['sources'][0]['url'] = aliased_repo
    full_mirror = mirror_repo.source_config()['url']
    mirror_map, _ = os.path.split(full_mirror)
    os.makedirs(element_dir)
    _yaml.dump(element, element_path)

    config_project_dir = str(tmpdir.join('config'))
    os.makedirs(config_project_dir, exist_ok=True)
    config_project = {
        'name': 'config'
    }
    _yaml.dump(config_project, os.path.join(config_project_dir, 'project.conf'))
    extra_mirrors = {
        'mirrors': [
            {
                'name': 'middle-earth',
                'aliases': {
                    alias: [mirror_map + "/"],
                }
            }
        ]
    }
    _yaml.dump(extra_mirrors, os.path.join(config_project_dir, 'mirrors.yml'))
    generate_junction(str(tmpdir.join('config_repo')),
                      config_project_dir,
                      os.path.join(element_dir, 'config.bst'))

    project = {
        'name': 'test',
        'element-path': 'elements',
        'aliases': {
            alias: upstream_map + "/"
        },
        '(@)': [
            'config.bst:mirrors.yml'
        ]
    }
    project_file = os.path.join(project_dir, 'project.conf')
    _yaml.dump(project, project_file)

    # Now make the upstream unavailable.
    os.rename(upstream_repo.repo, '{}.bak'.format(upstream_repo.repo))
    result = cli.run(project=project_dir, args=['source', 'fetch', element_name])
    result.assert_main_error(ErrorDomain.STREAM, None)
    # Now make the upstream available again.
    os.rename('{}.bak'.format(upstream_repo.repo), upstream_repo.repo)
    result = cli.run(project=project_dir, args=['source', 'fetch', element_name])
    result.assert_success()


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_mirror_track_upstream_present(cli, tmpdir, datafiles, kind):
    bin_files_path = os.path.join(str(datafiles), 'files', 'bin-files', 'usr')
    dev_files_path = os.path.join(str(datafiles), 'files', 'dev-files', 'usr')
    upstream_repodir = os.path.join(str(tmpdir), 'upstream')
    mirror_repodir = os.path.join(str(tmpdir), 'mirror')
    project_dir = os.path.join(str(tmpdir), 'project')
    os.makedirs(project_dir)
    element_dir = os.path.join(project_dir, 'elements')

    # Create repo objects of the upstream and mirror
    upstream_repo = create_repo(kind, upstream_repodir)
    upstream_repo.create(bin_files_path)
    mirror_repo = upstream_repo.copy(mirror_repodir)
    upstream_ref = upstream_repo.create(dev_files_path)

    element = {
        'kind': 'import',
        'sources': [
            upstream_repo.source_config(ref=upstream_ref)
        ]
    }

    element_name = 'test.bst'
    element_path = os.path.join(element_dir, element_name)
    full_repo = element['sources'][0]['url']
    upstream_map, repo_name = os.path.split(full_repo)
    alias = 'foo-' + kind
    aliased_repo = alias + ':' + repo_name
    element['sources'][0]['url'] = aliased_repo
    full_mirror = mirror_repo.source_config()['url']
    mirror_map, _ = os.path.split(full_mirror)
    os.makedirs(element_dir)
    _yaml.dump(element, element_path)

    project = {
        'name': 'test',
        'element-path': 'elements',
        'aliases': {
            alias: upstream_map + "/"
        },
        'mirrors': [
            {
                'name': 'middle-earth',
                'aliases': {
                    alias: [mirror_map + "/"],
                },
            },
        ]
    }
    project_file = os.path.join(project_dir, 'project.conf')
    _yaml.dump(project, project_file)

    result = cli.run(project=project_dir, args=['source', 'track', element_name])
    result.assert_success()

    # Tracking tries upstream first. Check the ref is from upstream.
    new_element = _yaml.load(element_path)
    source = new_element.get_sequence('sources').mapping_at(0)
    if 'ref' in source:
        assert source.get_str('ref') == upstream_ref


@pytest.mark.datafiles(DATA_DIR)
@pytest.mark.parametrize("kind", [(kind) for kind in ALL_REPO_KINDS])
def test_mirror_track_upstream_absent(cli, tmpdir, datafiles, kind):
    bin_files_path = os.path.join(str(datafiles), 'files', 'bin-files', 'usr')
    dev_files_path = os.path.join(str(datafiles), 'files', 'dev-files', 'usr')
    upstream_repodir = os.path.join(str(tmpdir), 'upstream')
    mirror_repodir = os.path.join(str(tmpdir), 'mirror')
    project_dir = os.path.join(str(tmpdir), 'project')
    os.makedirs(project_dir)
    element_dir = os.path.join(project_dir, 'elements')

    # Create repo objects of the upstream and mirror
    upstream_repo = create_repo(kind, upstream_repodir)
    upstream_ref = upstream_repo.create(bin_files_path)
    mirror_repo = upstream_repo.copy(mirror_repodir)
    mirror_ref = upstream_ref
    upstream_ref = upstream_repo.create(dev_files_path)

    element = {
        'kind': 'import',
        'sources': [
            upstream_repo.source_config(ref=upstream_ref)
        ]
    }

    element_name = 'test.bst'
    element_path = os.path.join(element_dir, element_name)
    full_repo = element['sources'][0]['url']
    _, repo_name = os.path.split(full_repo)
    alias = 'foo-' + kind
    aliased_repo = alias + ':' + repo_name
    element['sources'][0]['url'] = aliased_repo
    full_mirror = mirror_repo.source_config()['url']
    mirror_map, _ = os.path.split(full_mirror)
    os.makedirs(element_dir)
    _yaml.dump(element, element_path)

    project = {
        'name': 'test',
        'element-path': 'elements',
        'aliases': {
            alias: 'http://www.example.com/'
        },
        'mirrors': [
            {
                'name': 'middle-earth',
                'aliases': {
                    alias: [mirror_map + "/"],
                },
            },
        ]
    }
    project_file = os.path.join(project_dir, 'project.conf')
    _yaml.dump(project, project_file)

    result = cli.run(project=project_dir, args=['source', 'track', element_name])
    result.assert_success()

    # Check that tracking fell back to the mirror
    new_element = _yaml.load(element_path)
    source = new_element.get_sequence('sources').mapping_at(0)
    if 'ref' in source:
        assert source.get_str('ref') == mirror_ref
