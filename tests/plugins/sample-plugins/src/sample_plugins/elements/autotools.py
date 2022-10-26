#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
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

  .. literalinclude:: ../../../src/buildstream_plugins/elements/autotools.yaml
     :language: yaml

See `built-in functionality documentation
<https://docs.buildstream.build/master/buildstream.buildelement.html#core-buildelement-builtins>`_ for
details on common configuration options for build elements.
"""

from buildstream import BuildElement


# Element implementation for the 'autotools' kind.
class AutotoolsElement(BuildElement):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"


# Plugin entry point
def setup():
    return AutotoolsElement
