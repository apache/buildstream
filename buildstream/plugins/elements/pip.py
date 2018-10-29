#
#  Copyright (C) 2017 Mathieu Bridon
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
#  Authors:
#        Mathieu Bridon <bochecha@daitauha.fr>

"""
pip - Pip build element
=======================
A :mod:`BuildElement <buildstream.buildelement>` implementation for installing
Python modules with pip

The pip default configuration:
  .. literalinclude:: ../../../buildstream/plugins/elements/pip.yaml
     :language: yaml

See :ref:`built-in functionality documentation <core_buildelement_builtins>` for
details on common configuration options for build elements.
"""

from buildstream import BuildElement


# Element implementation for the 'pip' kind.
class PipElement(BuildElement):
    # This plugin has been modified to permit calling integration after staging
    BST_STAGE_INTEGRATES = False


# Plugin entry point
def setup():
    return PipElement
