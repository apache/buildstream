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

import os
import pytest

from tests.testutils import cli_integration as cli


pytestmark = pytest.mark.integration


# Project directory
DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "project",
)


@pytest.mark.integration
@pytest.mark.datafiles(DATA_DIR)
def test_artifact_log(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Get the cache key of our test element
    result = cli.run(project=project, silent=True, args=[
        '--no-colors',
        'show', '--deps', 'none', '--format', '%{full-key}',
        'base.bst'
    ])
    key = result.output.strip()

    # Ensure we have an artifact to read
    result = cli.run(project=project, args=['build', 'base.bst'])
    assert result.exit_code == 0

    # Read the log via the element name
    result = cli.run(project=project, args=['artifact', 'log', '-e', 'base.bst'])
    assert result.exit_code == 0
    log = result.output

    # Read the log via the key
    result = cli.run(project=project, args=['artifact', 'log', 'test/base/' + key])
    assert result.exit_code == 0
    assert log == result.output
