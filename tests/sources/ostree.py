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
#  Authors: William Salmon <will.salmon@codethink.co.uk>
#

import os
import pytest

from buildstream._exceptions import ErrorDomain
from buildstream import _yaml

from tests.testutils import cli, create_repo

DATA_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    'ostree',
)


@pytest.mark.datafiles(os.path.join(DATA_DIR, 'template'))
def test_submodule_track_no_ref_or_track(cli, tmpdir, datafiles):
    project = os.path.join(datafiles.dirname, datafiles.basename)

    # Create the repo from 'repofiles' subdir
    repo = create_repo('ostree', str(tmpdir))
    ref = repo.create(os.path.join(project, 'repofiles'))

    # Write out our test target
    ostreesource = repo.source_config(ref=None)
    ostreesource.pop('track')
    element = {
        'kind': 'import',
        'sources': [
            ostreesource
        ]
    }

    _yaml.dump(element, os.path.join(project, 'target.bst'))

    # Track will encounter an inconsistent submodule without any ref
    result = cli.run(project=project, args=['show', 'target.bst'])
    result.assert_main_error(ErrorDomain.SOURCE, "missing-track-and-ref")
    result.assert_task_error(None, None)
