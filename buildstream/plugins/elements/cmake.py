#
#  Copyright (C) 2016, 2018 Codethink Limited
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
cmake - CMake build element
===========================
This is a :mod:`BuildElement <buildstream.buildelement>` implementation for
using the `CMake <https://cmake.org/>`_ build system.

You will often want to pass additional arguments to the ``cmake`` program for
specific configuration options. This should be done on a per-element basis by
setting the ``cmake-local`` variable.  Here is an example:

.. code:: yaml

   variables:
     cmake-local: |
       -DCMAKE_BUILD_TYPE=Debug

If you want to pass extra options to ``cmake`` for every element in your
project, set the ``cmake-global`` variable in your project.conf file. Here is
an example of that:

.. code:: yaml

   elements:
     cmake:
       variables:
         cmake-global: |
           -DCMAKE_BUILD_TYPE=Release

Here is the default configuration for the ``cmake`` element in full:

  .. literalinclude:: ../../../buildstream/plugins/elements/cmake.yaml
     :language: yaml
"""

from buildstream import BuildElement


# Element implementation for the 'cmake' kind.
class CMakeElement(BuildElement):
    pass


# Plugin entry point
def setup():
    return CMakeElement
