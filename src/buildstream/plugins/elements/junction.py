#
#  Copyright (C) 2020 Codethink Limited
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
This element acts as a window into another BuildStream project. It allows integration
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

     # Optionally override junction configurations in the subproject
     # with a junction declaration in this project.
     #
     overrides:
       subproject-junction.bst: local-junction.bst

     # Optionally declare whether elements within the junction project
     # should interact with project remotes (default: False).
     cache-junction-elements: False

     # Optionally ignore junction remotes, this means that BuildStream
     # will not attempt to pull artifacts from the junction project's
     # remote(s) (default: False).
     ignore-junction-remotes: False

With a junction element in place, local elements can depend on elements in
the other BuildStream project using :ref:`element paths <format_element_names>`.
For example, if you have a ``toolchain.bst`` junction element referring to
a project which contains a ``gcc.bst`` element, you can express a build
dependency to the compiler like this:

.. code:: yaml

   build-depends:
   - junction: toolchain.bst:gcc.bst

.. important::

   **Limitations**

   Junction elements are only connectors which bring multiple projects together,
   and as such they are not in the element dependency graph. This means that it is
   illegal to depend on a junction, and it is also illegal for a junction to have
   dependencies.

   While junctions are elements, a limited set of element operations are
   supported. Junction elements can be tracked and fetched like other
   elements but they do not produce any artifacts, which means that they
   cannot be built or staged.

   Note that when running :ref:`bst source track <invoking_source_track>`
   on your project, elements found in subprojects are not tracked by default.
   You may specify ``--cross-junctions`` to the
   :ref:`bst source track <invoking_source_track>` command to explicitly track
   elements across junction boundaries.


Sources
-------
The sources of a junction element define how to obtain the BuildStream project
that the junction connects to.

Most commands, such as :ref:`bst build <invoking_build>`, will automatically
try to fetch the junction elements required to access any subproject elements which
are specified as dependencies of the targets provided.

Some commands, such as :ref:`bst show <invoking_show>`, do not do this, and in
such cases they can be fetched explicitly using
:ref:`bst source fetch <invoking_source_fetch>`:

.. code::

   bst source fetch junction.bst


Options
-------
Junction elements can configure the :ref:`project options <project_options>`
in the subproject, using the ``options`` configuration.

.. code:: yaml

   kind: junction

   ...

   config:

     # Specify the options for this subproject
     #
     options:
       machine_arch: "%{machine_arch}"
       debug: True

Options are never implicitly propagated across junctions, however
:ref:`variables <format_variables>` can be used to explicitly assign
configuration in a subproject which matches the toplevel project's
configuration.


.. _core_junction_nested:

Nested Junctions
----------------
Junctions can be nested. That is, subprojects are allowed to have junctions on
their own. Nested junctions in different subprojects may point to the same
project, however, in most use cases the same project should be loaded only once.

As the junctions may differ in source version and options, BuildStream cannot
simply use one junction and ignore the others. Due to this, BuildStream requires
the user to resolve conflicting nested junctions, and will provide an error
message whenever a conflict is detected.


Overriding subproject junctions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
If your project and a subproject share a subproject in common, then one way
to resolve the conflict is to override the subproject's junction with a local
in your project.

You can override junctions in a subproject in the junction declaration
of that subproject, e.g.:

.. code:: yaml

   kind: junction

   # Here we are junctioning "subproject" which
   # also junctions "subsubproject", which we also
   # use directly.
   #
   sources:
   - kind: git
     url: https://example.com/subproject.git

   config:
     # Override `subsubproject.bst` in the subproject using
     # the locally declared `local-subsubproject.bst` junction.
     #
     overrides:
       subsubproject.bst: local-subsubproject.bst

When declaring the ``overrides`` dictionary, the keys (on the left side)
refer to :ref:`junction paths <format_element_names>` which are relative
to the subproject you are declaring. The values (on the right side) refer
to :ref:`junction paths <format_element_names>` which are relative to the
project in which your junction is declared.

.. warning::

   This approach modifies your subproject, causing its output artifacts
   to differ from that project's expectations.

   If you rely on validation and guarantees provided by the organization
   which maintains the subproject, then it is desirable to avoid overriding
   any details from that upstream project.


Linking to other junctions
~~~~~~~~~~~~~~~~~~~~~~~~~~
Another way to resolve the conflict when your project and a subproject both
junction a common project, is to simply reuse the same junction from the
subproject in your toplevel project.

This is preferable to *overrides* because you can avoid modifying the
subproject you would otherwise be changing with an override.

A convenient way to reuse a nested junction in a higher level project
is to create a :mod:`link <elements.link>` element to that subproject's
junction. This will help you avoid redundantly typing out longer
:ref:`element paths <format_element_names>` in your project's
:ref:`dependency declarations <format_dependencies>`.

This way you can simply create the :mod:`link <elements.link>` once
in your project and use it locally to depend on elements in a nested
subproject.

**Example:**

.. code:: yaml

   # Declare the `subsubproject-link.bst` link element, which
   # is a symbolic link to the junction declared in the subproject
   #
   kind: link

   config:
     target: subproject.bst:subsubproject.bst


.. code:: yaml

   # Depend on elements in the subsubproject using
   # the subproject's junction directly
   #
   kind: autotools

   depends:
   - subsubproject-link.bst:glibc.bst


.. tip::

   When reconciling conflicting junction declarations to the
   same subproject, it is also possible to use a locally defined
   :mod:`link <elements.link>` element from one subproject to
   override another junction to the same project in an adjacent
   subproject.


Multiple project instances
~~~~~~~~~~~~~~~~~~~~~~~~~~
By default, loading the same project more than once will result
in a *conflicting junction error*. There are some use cases which
demand that you load the same project more than once in the same
build pipeline.

In order to allow the loading of multiple instances of the same project
in the same build pipeline, please refer to the
:ref:`relevant project.conf documentation <project_junctions>`.
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

        node.validate_keys(["path", "options", "cache-junction-elements", "ignore-junction-remotes", "overrides"])

        self.path = node.get_str("path", default="")
        self.options = node.get_mapping("options", default={})
        self.cache_junction_elements = node.get_bool("cache-junction-elements", default=False)
        self.ignore_junction_remotes = node.get_bool("ignore-junction-remotes", default=False)

        # The overrides dictionary has the target junction
        # to override as a key, and a tuple consisting
        # of the local overriding junction and the provenance
        # of the override declaration.
        self.overrides = {}
        overrides_node = node.get_mapping("overrides", {})
        for key, value in overrides_node.items():
            junction_name = value.as_str()
            provenance = value.get_provenance()

            # Cannot override a subproject with the project itself
            #
            if junction_name == self.name:
                raise ElementError(
                    "{}: Attempt to override subproject junction '{}' with the overriding junction '{}' itself".format(
                        provenance, key, junction_name
                    ),
                    reason="override-junction-with-self",
                )
            self.overrides[key] = (junction_name, provenance)

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
