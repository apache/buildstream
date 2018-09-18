#
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
#  Authors: Chandan Singh <csingh43@bloomberg.net>
#

import os
import tarfile

import pytest

from tests.testutils import cli

# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.datafiles(DATA_DIR)
def test_source_bundle(cli, tmpdir, datafiles):
    project_path = os.path.join(datafiles.dirname, datafiles.basename)
    element_name = 'source-bundle/source-bundle-hello.bst'
    normal_name = 'source-bundle-source-bundle-hello'

    # Verify that we can correctly produce a source-bundle
    args = ['source-bundle', element_name, '--directory', str(tmpdir)]
    result = cli.run(project=project_path, args=args)
    result.assert_success()

    # Verify that the source-bundle contains our sources and a build script
    with tarfile.open(os.path.join(str(tmpdir), '{}.tar.gz'.format(normal_name))) as bundle:
        assert os.path.join(normal_name, 'source', normal_name, 'llamas.txt') in bundle.getnames()
        assert os.path.join(normal_name, 'build.sh') in bundle.getnames()
