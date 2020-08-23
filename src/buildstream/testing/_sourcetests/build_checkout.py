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
from .base import BaseSourceTests


def strict_args(args, strict):
    if strict != "strict":
        return ["--no-strict", *args]
    return args


class BuildCheckoutSourceTests(BaseSourceTests):
    @pytest.mark.parametrize("strict", ["strict", "non-strict"])
    def test_fetch_build_checkout(self, cli, tmpdir, datafiles, strict):
        checkout = os.path.join(cli.directory, "checkout")
        project = str(datafiles)
        dev_files_path = os.path.join(project, "files", "dev-files")
        element_path = os.path.join(project, "elements")
        element_name = "build-test-{}.bst".format(self.KIND)

        # Create our repo object of the given source type with
        # the dev files, and then collect the initial ref.
        #
        repo = self.REPO(str(tmpdir))
        ref = repo.create(dev_files_path)

        # Write out our test target
        element = {"kind": "import", "sources": [repo.source_config(ref=ref)]}
        _yaml.roundtrip_dump(element, os.path.join(element_path, element_name))

        assert cli.get_element_state(project, element_name) == "fetch needed"
        result = cli.run(project=project, args=strict_args(["build", element_name], strict))
        result.assert_success()
        assert cli.get_element_state(project, element_name) == "cached"

        # Now check it out
        result = cli.run(
            project=project, args=strict_args(["artifact", "checkout", element_name, "--directory", checkout], strict)
        )
        result.assert_success()

        # Check that the pony.h include from files/dev-files exists
        filename = os.path.join(checkout, "usr", "include", "pony.h")
        assert os.path.exists(filename)
