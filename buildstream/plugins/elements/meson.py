#  Copyright (C) 2017 Patrick Griffis
#  Copyright (C) 2018 Codethink Ltd.
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

"""
meson - Meson build element
===========================
This is a :mod:`BuildElement <buildstream.buildelement>` implementation for
using `Meson <http://mesonbuild.com/>`_ build scripts.

You will often want to pass additional arguments to ``meson``. This should
be done on a per-element basis by setting the ``meson-local`` variable.  Here is
an example:

.. code:: yaml

   variables:
     meson-local: |
       -Dmonkeys=yes

If you want to pass extra options to ``meson`` for every element in your
project, set the ``meson-global`` variable in your project.conf file. Here is
an example of that:

.. code:: yaml

   elements:
     meson:
       variables:
         meson-global: |
           -Dmonkeys=always

Here is the default configuration for the ``meson`` element in full:

  .. literalinclude:: ../../../buildstream/plugins/elements/meson.yaml
     :language: yaml
"""

from buildstream import BuildElement


# Element implementation for the 'meson' kind.
class MesonElement(BuildElement):
    pass


# Plugin entry point
def setup():
    return MesonElement
