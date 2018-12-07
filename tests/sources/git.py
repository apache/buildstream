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
#  Authors: Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#           Jonathan Maw <jonathan.maw@codethink.co.uk>
#           William Salmon <will.salmon@codethink.co.uk>
#

import os
import pytest
import shutil

from buildstream._exceptions import ErrorDomain
from buildstream import _yaml

from tests.testutils import cli, create_repo
from tests.testutils.site import HAVE_GIT

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'git',
)


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_fetch_bad_ref(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Create the repo from 'repofiles' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project, 'repofiles'))

    # Write out our test target with a bad ref
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref='5')
        ]
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Assert that fetch raises an error here
    result = cli.run(project=project, args=[
        'fetch', 'target.bst'
    ])
    result.assert_main_error(ErrorDomain.STREAM, None)
    result.assert_task_error(ErrorDomain.SOURCE, None)


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_fetch_checkout(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo('git', str(tmpdir), 'subrepo')
    subref = subrepo.create(os.path.join(project, 'subrepofiles'))

    # Create the repo from 'repofiles' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project, 'repofiles'))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule('subdir', 'file://' + subrepo.repo)

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Fetch, build, checkout
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Assert we checked out both files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, 'file.txt'))
    assert os.path.exists(os.path.join(checkoutdir, 'subdir', 'ponyfile.txt'))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_fetch_source_enable_explicit(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo('git', str(tmpdir), 'subrepo')
    subrepo.create(os.path.join(project, 'subrepofiles'))

    # Create the repo from 'repofiles' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project, 'repofiles'))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule('subdir', 'file://' + subrepo.repo)

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref, checkout_submodules=True)
        ]
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Fetch, build, checkout
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Assert we checked out both files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, 'file.txt'))
    assert os.path.exists(os.path.join(checkoutdir, 'subdir', 'ponyfile.txt'))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_fetch_source_disable(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo('git', str(tmpdir), 'subrepo')
    subrepo.create(os.path.join(project, 'subrepofiles'))

    # Create the repo from 'repofiles' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project, 'repofiles'))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule('subdir', 'file://' + subrepo.repo)

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref, checkout_submodules=False)
        ]
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Fetch, build, checkout
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Assert we checked out both files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, 'file.txt'))
    assert not os.path.exists(os.path.join(checkoutdir, 'subdir', 'ponyfile.txt'))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_fetch_submodule_does_override(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo('git', str(tmpdir), 'subrepo')
    subrepo.create(os.path.join(project, 'subrepofiles'))

    # Create the repo from 'repofiles' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project, 'repofiles'))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule('subdir', 'file://' + subrepo.repo, checkout=True)

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref, checkout_submodules=False)
        ]
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Fetch, build, checkout
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Assert we checked out both files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, 'file.txt'))
    assert os.path.exists(os.path.join(checkoutdir, 'subdir', 'ponyfile.txt'))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_fetch_submodule_individual_checkout(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo('git', str(tmpdir), 'subrepo')
    subrepo.create(os.path.join(project, 'subrepofiles'))

    # Create another submodule from the 'othersubrepofiles' subdir
    other_subrepo = create_repo('git', str(tmpdir), 'othersubrepo')
    other_subrepo.create(os.path.join(project, 'othersubrepofiles'))

    # Create the repo from 'repofiles' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project, 'repofiles'))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule('subdir', 'file://' + subrepo.repo, checkout=False)
    ref = repo.add_submodule('othersubdir', 'file://' + other_subrepo.repo)

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref, checkout_submodules=True)
        ]
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Fetch, build, checkout
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Assert we checked out files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, 'file.txt'))
    assert not os.path.exists(os.path.join(checkoutdir, 'subdir', 'ponyfile.txt'))
    assert os.path.exists(os.path.join(checkoutdir, 'othersubdir', 'unicornfile.txt'))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_fetch_submodule_individual_checkout_explicit(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo('git', str(tmpdir), 'subrepo')
    subrepo.create(os.path.join(project, 'subrepofiles'))

    # Create another submodule from the 'othersubrepofiles' subdir
    other_subrepo = create_repo('git', str(tmpdir), 'othersubrepo')
    other_subrepo.create(os.path.join(project, 'othersubrepofiles'))

    # Create the repo from 'repofiles' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project, 'repofiles'))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule('subdir', 'file://' + subrepo.repo, checkout=False)
    ref = repo.add_submodule('othersubdir', 'file://' + other_subrepo.repo, checkout=True)

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref, checkout_submodules=True)
        ]
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Fetch, build, checkout
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Assert we checked out files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, 'file.txt'))
    assert not os.path.exists(os.path.join(checkoutdir, 'subdir', 'ponyfile.txt'))
    assert os.path.exists(os.path.join(checkoutdir, 'othersubdir', 'unicornfile.txt'))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'project-override'))
def test_submodule_fetch_project_override(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)
    checkoutdir = os.path.join(str(tmpdir), "checkout")

    # Create the submodule first from the 'subrepofiles' subdir
    subrepo = create_repo('git', str(tmpdir), 'subrepo')
    subrepo.create(os.path.join(project, 'subrepofiles'))

    # Create the repo from 'repofiles' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project, 'repofiles'))

    # Add a submodule pointing to the one we created
    ref = repo.add_submodule('subdir', 'file://' + subrepo.repo)

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Fetch, build, checkout
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
    result = cli.run(project=project, args=['checkout', 'target.bst', checkoutdir])
    result.assert_success()

    # Assert we checked out both files at their expected location
    assert os.path.exists(os.path.join(checkoutdir, 'file.txt'))
    assert not os.path.exists(os.path.join(checkoutdir, 'subdir', 'ponyfile.txt'))


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_track_ignore_inconsistent(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Create the repo from 'repofiles' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project, 'repofiles'))

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            repo.source_config(ref=ref)
        ]
    }
    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Now add a .gitmodules file with an inconsistent submodule,
    # we are calling this inconsistent because the file was created
    # but `git submodule add` was never called, so there is no reference
    # associated to the submodule.
    #
    repo.add_file(os.path.join(project, 'inconsistent-submodule', '.gitmodules'))

    # Fetch should work, we're not yet at the offending ref
    result = cli.run(project=project, args=['fetch', 'target.bst'])
    result.assert_success()

    # Track will encounter an inconsistent submodule without any ref
    result = cli.run(project=project, args=['track', 'target.bst'])
    result.assert_success()

    # Assert that we are just fine without it, and emit a warning to the user.
    assert "Ignoring inconsistent submodule" in result.stderr


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_track_no_ref_or_track(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Create the repo from 'repofiles' subdir
    repo = create_repo('git', str(tmpdir))
    ref = repo.create(os.path.join(project, 'repofiles'))

    # Write out our test target
    gitsource = repo.source_config(ref=None)
    gitsource.pop('track')
    element = {
        'kind': 'import',
        'sources': [
            gitsource
        ]
    }

    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Track will encounter an inconsistent submodule without any ref
    result = cli.run(project=project, args=['show', 'target.bst'])
    result.assert_main_error(ErrorDomain.SOURCE, "missing-track-and-ref")
    result.assert_task_error(None, None)


@pytest.mark.skipif(HAVE_GIT is False, reason="git is not available")
@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_overwrite_rogue_tag_multiple_remotes(cli, tmpdir, datafiles):
    """When using multiple remotes in cache (i.e. when using aliases), we
    need to make sure we override tags. This is not allowed to fetch
    tags that were present from different origins
    """

    project = str(datafiles)

    repofiles = os.path.join(str(tmpdir), 'repofiles')
    os.makedirs(repofiles, exist_ok=True)
    file0 = os.path.join(repofiles, 'file0')
    with open(file0, 'w') as f:
        f.write('test\n')

    repo = create_repo('git', str(tmpdir))

    top_commit = repo.create(repofiles)

    repodir, reponame = os.path.split(repo.repo)
    project_config = _yaml.load(os.path.join(project, 'project.conf'))
    project_config['aliases'] = {
        'repo': 'http://example.com/'
    }
    project_config['mirrors'] = [
        {
            'name': 'middle-earth',
            'aliases': {
                'repo': ['file://{}/'.format(repodir)]
            }
        }
    ]
    _yaml.dump(_yaml.node_sanitize(project_config), os.path.join(project, 'project.conf'))

    repo.add_annotated_tag('tag', 'tag')

    file1 = os.path.join(repofiles, 'file1')
    with open(file1, 'w') as f:
        f.write('test\n')

    ref = repo.add_file(file1)

    config = repo.source_config(ref=ref)
    del config['track']
    config['url'] = 'repo:{}'.format(reponame)

    # Write out our test target
    element = {
        'kind': 'import',
        'sources': [
            config
        ],
    }
    element_path = os.path.join(project, 'target.bst')
    _yaml.dump(element, element_path)

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()

    repo.checkout(top_commit)

    file2 = os.path.join(repofiles, 'file2')
    with open(file2, 'w') as f:
        f.write('test\n')

    new_ref = repo.add_file(file2)

    repo.delete_tag('tag')
    repo.add_annotated_tag('tag', 'tag')
    repo.checkout('master')

    otherpath = os.path.join(str(tmpdir), 'other_path')
    shutil.copytree(repo.repo,
                    os.path.join(otherpath, 'repo'))
    new_repo = create_repo('git', otherpath)

    repodir, reponame = os.path.split(repo.repo)

    _yaml.dump(_yaml.node_sanitize(project_config), os.path.join(project, 'project.conf'))

    config = repo.source_config(ref=new_ref)
    del config['track']
    config['url'] = 'repo:{}'.format(reponame)

    element = {
        'kind': 'import',
        'sources': [
            config
        ],
    }
    _yaml.dump(element, element_path)

    result = cli.run(project=project, args=['build', 'target.bst'])
    result.assert_success()
