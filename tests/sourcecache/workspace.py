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
import os
import pytest
import shutil

from buildstream.plugintestutils.runcli import cli

from tests.testutils.element_generators import create_element_size


DATA_DIR = os.path.dirname(os.path.realpath(__file__))


# Test that when we have sources only in the local CAS buildstream fetches them
# for opening a workspace
@pytest.mark.datafiles(DATA_DIR)
def test_workspace_source_fetch(tmpdir, datafiles, cli):
    project_dir = os.path.join(str(tmpdir), 'project')
    element_path = 'elements'
    source_dir = os.path.join(str(tmpdir), 'cache', 'sources')
    workspace = os.path.join(cli.directory, 'workspace')

    cli.configure({
        'cachedir': os.path.join(str(tmpdir), 'cache')
    })

    create_element_size('target.bst', project_dir, element_path, [], 10000)
    res = cli.run(project=project_dir, args=['build', 'target.bst'])
    res.assert_success()
    assert 'Fetching from' in res.stderr

    # remove the original sources
    shutil.rmtree(source_dir)

    # Open a workspace and check that fetches the original sources
    res = cli.run(project=project_dir,
                  args=['workspace', 'open', 'target.bst', '--directory', workspace])
    res.assert_success()
    assert 'Fetching from' in res.stderr

    assert os.listdir(workspace) != []
