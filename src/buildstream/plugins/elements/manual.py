#
#  Copyright (C) 2016 Codethink Limited
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
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>

"""
manual - Manual build element
=============================
The most basic build element does nothing but allows users to
add custom build commands to the array understood by the :mod:`BuildElement <buildstream.buildelement>`

The empty configuration is as such:
  .. literalinclude:: ../../../src/buildstream/plugins/elements/manual.yaml
     :language: yaml

See :ref:`built-in functionality documentation <core_buildelement_builtins>` for
details on common configuration options for build elements.
"""

from buildstream import BuildElement, SandboxFlags


# Element implementation for the 'manual' kind.
class ManualElement(BuildElement):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    # Enable command batching across prepare() and assemble()
    def configure_sandbox(self, sandbox):
        super().configure_sandbox(sandbox)
        self.batch_prepare_assemble(SandboxFlags.ROOT_READ_ONLY, collect=self.get_variable("install-root"))


# Plugin entry point
def setup():
    return ManualElement
