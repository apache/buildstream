#
#  Copyright (C) 2018 Codethink Limited
#  Copyright (C) 2020 Bloomberg Finance LP
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

import os
import pytest

from buildstream import _yaml
from .._utils import generate_junction
from .utils import update_project_configuration
from .base import BaseSourceTests


class FetchSourceTests(BaseSourceTests):
    def test_fetch(self, cli, tmpdir, datafiles):
        project = str(datafiles)
        bin_files_path = os.path.join(project, "files", "bin-files")
        element_path = os.path.join(project, "elements")
        element_name = "fetch-test-{}.bst".format(self.KIND)

        # Create our repo object of the given source type with
        # the bin files, and then collect the initial ref.
        #
        repo = self.REPO(str(tmpdir))
        ref = repo.create(bin_files_path)

        # Write out our test target
        element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
        _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

        # Assert that a fetch is needed
        assert cli.get_element_state(project, element_name) == "fetch needed"

        # Now try to fetch it
        result = cli.run(project=project, args=["source", "fetch", element_name])
        result.assert_success()

        # Assert that we are now buildable because the source is
        # now cached.
        assert cli.get_element_state(project, element_name) == "buildable"

    @pytest.mark.parametrize("ref_storage", ["inline", "project.refs"])
    def test_fetch_cross_junction(self, cli, tmpdir, datafiles, ref_storage):
        project = str(datafiles)
        subproject_path = os.path.join(project, "files", "sub-project")
        junction_path = os.path.join(project, "elements", "junction.bst")

        import_etc_path = os.path.join(subproject_path, "elements", "import-etc-repo.bst")
        etc_files_path = os.path.join(subproject_path, "files", "etc-files")

        repo = self.REPO(str(tmpdir.join("import-etc")))
        ref = repo.create(etc_files_path)

        element = {"kind": "import", "sources": [repo.source_config(ref=(ref if ref_storage == "inline" else None))]}
        _yaml.roundtrip_dump(element, import_etc_path)

        update_project_configuration(project, {"ref-storage": ref_storage})

        generate_junction(tmpdir, subproject_path, junction_path, store_ref=(ref_storage == "inline"))

        if ref_storage == "project.refs":
            result = cli.run(project=project, args=["source", "track", "junction.bst"])
            result.assert_success()
            result = cli.run(project=project, args=["source", "track", "junction.bst:import-etc.bst"])
            result.assert_success()

        result = cli.run(project=project, args=["source", "fetch", "junction.bst:import-etc.bst"])
        result.assert_success()
