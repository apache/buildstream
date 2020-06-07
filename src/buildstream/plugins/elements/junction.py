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

     # Optionally declare whether elements within the junction project
     # should interact with project remotes (default: False).
     cache-junction-elements: False

     # Optionally ignore junction remotes, this means that BuildStream
     # will not attempt to pull artifacts from the junction project's
     # remote(s) (default: False).
     ignore-junction-remotes: False

.. note::

   Junction elements may not specify any dependencies as they are simply
   links to other projects and are not in the dependency graph on their own.

With a junction element in place, local elements can depend on elements in
the other BuildStream project using :ref:`element paths <format_element_names>`.
For example, if you have a ``toolchain.bst`` junction element referring to
a project which contains a ``gcc.bst`` element, you can express a build
dependency to the compiler like this:

.. code:: yaml

   build-depends:
   - junction: toolchain.bst:gcc.bst

While junctions are elements, only a limited set of element operations is
supported. They can be tracked and fetched like other elements.
However, junction elements do not produce any artifacts, which means that
they cannot be built or staged. It also means that another element cannot
depend on a junction element itself.

.. note::

   Elements within the subproject are not tracked by default when running
   `bst source track`. You must specify `--cross-junctions` to the track
   command to explicitly do it.


Sources
-------
``bst show`` does not implicitly fetch junction sources if they haven't been
cached yet. However, they can be fetched explicitly:

.. code::

   bst source fetch junction.bst

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

.. _core_junction_nested:

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

Linking to other junctions
~~~~~~~~~~~~~~~~~~~~~~~~~~
When working with nested junctions, you often need to ensure that multiple
projects are using the same version of a given subproject.

In order to ensure that your project is using a junction to a sub-subproject
declared by a direct subproject, then you can use a :mod:`link <elements.link>`
element in place of declaring a junction.

This lets you create a link to a junction in the subproject, which you
can then treat as a regular junction in your toplevel project.

.. code:: yaml

   kind: link

   config:
     target: subproject.bst:subsubproject.bst
"""

from buildstream import Element, ElementError
from buildstream._pipeline import PipelineError


# Element implementation for the 'junction' kind.
class JunctionElement(Element):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    # Junctions are not allowed any dependencies
    BST_FORBID_BDEPENDS = True
    BST_FORBID_RDEPENDS = True

    def configure(self, node):

        node.validate_keys(["path", "options", "cache-junction-elements", "ignore-junction-remotes"])

        self.path = node.get_str("path", default="")
        self.options = node.get_mapping("options", default={})
        self.cache_junction_elements = node.get_bool("cache-junction-elements", default=False)
        self.ignore_junction_remotes = node.get_bool("ignore-junction-remotes", default=False)

    def preflight(self):
        pass

    def get_unique_key(self):
        # Junctions do not produce artifacts. get_unique_key() implementation
        # is still required for `bst source fetch`.
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
