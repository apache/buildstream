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
makemaker - Perl MakeMaker build element
========================================
A :mod:`BuildElement <buildstream.buildelement>` implementation for using
the Perl ExtUtil::MakeMaker build system

The MakeMaker default configuration:
  .. literalinclude:: ../../../src/buildstream/plugins/elements/makemaker.yaml
     :language: yaml

See :ref:`built-in functionality documentation <core_buildelement_builtins>` for
details on common configuration options for build elements.
"""

from buildstream import BuildElement, SandboxFlags


# Element implementation for the 'makemaker' kind.
class MakeMakerElement(BuildElement):
    # Supports virtual directories (required for remote execution)
    BST_VIRTUAL_DIRECTORY = True

    # Enable command batching across prepare() and assemble()
    def configure_sandbox(self, sandbox):
        super().configure_sandbox(sandbox)
        self.batch_prepare_assemble(SandboxFlags.ROOT_READ_ONLY,
                                    collect=self.get_variable('install-root'))


# Plugin entry point
def setup():
    return MakeMakerElement
