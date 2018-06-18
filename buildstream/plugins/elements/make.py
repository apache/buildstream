#
#  Copyright Bloomberg Finance LP
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
#        Ed Baunton <ebaunton1@bloomberg.net>

"""
make - Make build element
=========================
This is a :mod:`BuildElement <buildstream.buildelement>` implementation for
using GNU make based build.

.. note::

   The ``make`` element is available since :ref:`format version 9 <project_format_version>`

Here is the default configuration for the ``make`` element in full:

  .. literalinclude:: ../../../buildstream/plugins/elements/make.yaml
     :language: yaml
"""

from buildstream import BuildElement


# Element implementation for the 'make' kind.
class MakeElement(BuildElement):
    pass


# Plugin entry point
def setup():
    return MakeElement
