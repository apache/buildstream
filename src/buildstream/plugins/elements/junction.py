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

     # Optionally override elements in subprojects, including junctions.
     #
     overrides:
       subproject-junction.bst: local-junction.bst

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


Overriding elements
-------------------
It is possible to override elements in subprojects. This can be useful if for
example, you need to work with a custom variant or fork of some software in the
subproject. This is a better strategy than overlapping and overwriting shared
libraries built by the subproject later on, as we can ensure that reverse dependencies
in the subproject are built against the overridden element.

Overridding elements allows you to build on top of an existing project
and benefit from updates and releases for the vast majority of the upstream project,
even when there are some parts of the upstream project which need to be customized
for your own applications.

Even junction elements in subprojects can be overridden, this is sometimes important
in order to reconcile conflicts when multiple projects depend on the same subproject,
as :ref:`discussed below <core_junction_nested_overrides>`.

.. code:: yaml

   kind: junction

   ...

   config:

     # Override elements in a junctioned project
     #
     overrides:
       subproject-element.bst: local-element.bst

It is also possible to override elements in deeply nested subprojects, using
project relative :ref:`junction paths <format_element_names>`:

.. code:: yaml

   kind: junction

   ...

   config:

     # Override deeply nested elements
     #
     overrides:
       subproject.bst:subsubproject-element.bst: local-element.bst

.. attention::

   Overriding an element causes your project to completely define the
   element being overridden, which means you will no longer receive updates
   or security patches to the element in question when updating to newer
   versions and releases of the upstream project.

   As such, overriding elements is only recommended in cases where the
   element is very significantly redefined.

   Such cases include cases when you need a newer version of the element than
   the one maintained by the upstream project you are using as a subproject,
   or when you have significanly modified the code in your own custom ways.

   If you only need to introduce a security patch, then it is recommended that
   you create your own downstream branch of the upstream project, not only will
   this allow you to more easily consume updates with VCS tools like ``git rebase``,
   but it will also be more convenient for submitting your security patches
   to the upstream project so that you can drop them in a future update.

   Similarly, if you only need to enable/disable a specific feature of a module,
   it is also preferrable to use a downstream branch of the upstream project.
   In such a case, it is also worth trying to convince the upstream project to
   support a :ref:`project option <project_options>` for your specific element
   configuration, if it would be of use to other users too.


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


.. _core_junction_nested_overrides:

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

        node.validate_keys(["path", "options", "overrides"])

        self.path = node.get_str("path", default="")
        self.options = node.get_mapping("options", default={})

        # The overrides dictionary has the target junction
        # to override as a key, and the ScalarNode of the
        # junction name as a value
        self.overrides = {}
        overrides_node = node.get_mapping("overrides", {})
        for key, junction_name in overrides_node.items():

            # Cannot override a subproject with the project itself
            #
            if junction_name.as_str() == self.name:
                raise ElementError(
                    "{}: Attempt to override subproject junction '{}' with the overriding junction '{}' itself".format(
                        junction_name.get_provenance(), key, junction_name.as_str()
                    ),
                    reason="override-junction-with-self",
                )
            self.overrides[key] = junction_name

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
