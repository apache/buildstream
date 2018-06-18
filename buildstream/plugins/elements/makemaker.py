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
  .. literalinclude:: ../../../buildstream/plugins/elements/makemaker.yaml
     :language: yaml
"""

from buildstream import BuildElement


# Element implementation for the 'makemaker' kind.
class MakeMakerElement(BuildElement):
    pass


# Plugin entry point
def setup():
    return MakeMakerElement
