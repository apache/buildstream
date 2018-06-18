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
autotools - Autotools build element
===================================
This is a :mod:`BuildElement <buildstream.buildelement>` implementation for
using Autotools build scripts (also known as the `GNU Build System
<https://en.wikipedia.org/wiki/GNU_Build_System>`_).

You will often want to pass additional arguments to ``configure``. This should
be done on a per-element basis by setting the ``conf-local`` variable.  Here is
an example:

.. code:: yaml

   variables:
     conf-local: |
       --disable-foo --enable-bar

If you want to pass extra options to ``configure`` for every element in your
project, set the ``conf-global`` variable in your project.conf file. Here is
an example of that:

.. code:: yaml

   elements:
     autotools:
       variables:
         conf-global: |
           --disable-gtk-doc --disable-static

Here is the default configuration for the ``autotools`` element in full:

  .. literalinclude:: ../../../buildstream/plugins/elements/autotools.yaml
     :language: yaml
"""

from buildstream import BuildElement


# Element implementation for the 'autotools' kind.
class AutotoolsElement(BuildElement):
    pass


# Plugin entry point
def setup():
    return AutotoolsElement
