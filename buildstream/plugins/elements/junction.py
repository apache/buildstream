#
#  Copyright (C) 2017 Codethink Limited
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
#        Jürg Billeter <juerg.billeter@codethink.co.uk>

"""
junction - Integrate subprojects
================================
This element is a link to another BuildStream project. It allows integration
of multiple projects into a single pipeline.

Overview
--------

.. code:: yaml

   kind: junction

   # Specify the BuildStream project source
   sources:
   - kind: git
     url: upstream:projectname.git
     track: master
     ref: d0b38561afb8122a3fc6bafc5a733ec502fcaed6

   # Specify the junction configuration
   config:

     # Override project options
     options:
       machine_arch: "%{machine_arch}"
       debug: True

     # Optionally look in a subpath of the source repository for the project
     path: projects/hello

.. note::

   Junction elements may not specify any dependencies as they are simply
   links to other projects and are not in the dependency graph on their own.

With a junction element in place, local elements can depend on elements in
the other BuildStream project using the additional ``junction`` attribute in the
dependency dictionary:

.. code:: yaml

   depends:
   - junction: toolchain.bst
     filename: gcc.bst
     type: build

While junctions are elements, only a limited set of element operations is
supported. They can be tracked and fetched like other elements.
However, junction elements do not produce any artifacts, which means that
they cannot be built or staged. It also means that another element cannot
depend on a junction element itself.

.. note::

   BuildStream does not implicitly track junction elements. This means
   that if we were to invoke: `bst build --track-all ELEMENT` on an element
   which uses a junction element, the ref of the junction element
   will not automatically be updated if a more recent version exists.

   Therefore, if you require the most up-to-date version of a subproject,
   you must explicitly track the junction element by invoking:
   `bst track JUNCTION_ELEMENT`.

   Furthermore, elements within the subproject are also not tracked by default.
   For this, we must specify the `--track-cross-junctions` option. This option
   must be preceeded by `--track ELEMENT` or `--track-all`.


Sources
-------
``bst show`` does not implicitly fetch junction sources if they haven't been
cached yet. However, they can be fetched explicitly:

.. code::

   bst fetch junction.bst

Other commands such as ``bst build`` implicitly fetch junction sources.

Options
-------
.. code:: yaml

   options:
     machine_arch: "%{machine_arch}"
     debug: True

Junctions can configure options of the linked project. Options are never
implicitly inherited across junctions, however, variables can be used to
explicitly assign the same value to a subproject option.

Nested Junctions
----------------
Junctions can be nested. That is, subprojects are allowed to have junctions on
their own. Nested junctions in different subprojects may point to the same
project, however, in most use cases the same project should be loaded only once.
BuildStream uses the junction element name as key to determine which junctions
to merge. It is recommended that the name of a junction is set to the same as
the name of the linked project.

As the junctions may differ in source version and options, BuildStream cannot
simply use one junction and ignore the others. Due to this, BuildStream requires
the user to resolve possibly conflicting nested junctions by creating a junction
with the same name in the top-level project, which then takes precedence.
"""

from collections import Mapping
from buildstream import Element
from buildstream._pipeline import PipelineError


# Element implementation for the 'junction' kind.
class JunctionElement(Element):
    # pylint: disable=attribute-defined-outside-init

    # Junctions are not allowed any dependencies
    BST_FORBID_BDEPENDS = True
    BST_FORBID_RDEPENDS = True

    def configure(self, node):
        self.path = self.node_get_member(node, str, 'path', default='')
        self.options = self.node_get_member(node, Mapping, 'options', default={})

    def preflight(self):
        pass

    def get_unique_key(self):
        # Junctions do not produce artifacts. get_unique_key() implementation
        # is still required for `bst fetch`.
        return 1

    def configure_sandbox(self, sandbox):
        raise PipelineError("Cannot build junction elements")

    def stage(self, sandbox):
        raise PipelineError("Cannot stage junction elements")

    def generate_script(self):
        raise PipelineError("Cannot build junction elements")

    def assemble(self, sandbox):
        raise PipelineError("Cannot build junction elements")


# Plugin entry point
def setup():
    return JunctionElement
