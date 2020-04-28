#
#  Copyright (C) 2018 Codethink Limited
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
#        Jonathan Maw <jonathan.maw@codethink.co.uk>

"""
filter - Extract a subset of files from another element
=======================================================
Filter another element by producing an output that is a subset of
the parent element's output. Subsets are defined by the parent element's
:ref:`split rules <public_split_rules>`.

Overview
--------
A filter element must have exactly one *build* dependency, where said
dependency is the 'parent' element which we would like to filter.
Runtime dependencies may also be specified, which can be useful to propagate
forward from this filter element onto its reverse dependencies.
See :ref:`Dependencies <format_dependencies>` to see how we specify dependencies.

When workspaces are opened, closed or reset on a filter element, or this
element is tracked, the filter element will transparently pass on the command
to its parent element (the sole build-dependency).

Example
-------
Consider a simple import element, ``import.bst`` which imports the local files
'foo', 'bar' and 'baz' (each stored in ``files/``, relative to the project's root):

.. code:: yaml

   kind: import

   # Specify sources to import
   sources:
   - kind: local
     path: files

   # Specify public domain data, visible to other elements
   public:
     bst:
       split-rules:
         foo:
         - /foo
         bar:
         - /bar

.. note::

   We can make an element's metadata visible to all reverse dependencies by making use
   of the ``public:`` field. See the :ref:`public data documentation <format_public>`
   for more information.

In this example, ``import.bst`` will serve as the 'parent' of the filter element, thus
its output will be filtered. It is important to understand that the artifact of the
above element will contain the files: 'foo', 'bar' and 'baz'.

Now, to produce an element whose artifact contains the file 'foo', and exlusively 'foo',
we can define the following filter, ``filter-foo.bst``:

.. code:: yaml

   kind: filter

   # Declare the sole build-dependency of the filter element
   build-depends:
   - import.bst

   # Declare a list of domains to include in the filter's artifact
   config:
     include:
     - foo

It should be noted that an 'empty' ``include:`` list would, by default, include all
split-rules specified in the parent element, which, in this example, would be the
files 'foo' and 'bar' (the file 'baz' was not covered by any split rules).

Equally, we can use the ``exclude:`` statement to create the same artifact (which
only contains the file 'foo') by declaring the following element, ``exclude-bar.bst``:

.. code:: yaml

   kind: filter

   # Declare the sole build-dependency of the filter element
   build-depends:
   - import.bst

   # Declare a list of domains to exclude in the filter's artifact
   config:
     exclude:
     - bar

In addition to the ``include:`` and ``exclude:`` fields, there exists an ``include-orphans:``
(Boolean) field, which defaults to ``False``. This will determine whether to include files
which are not present in the 'split-rules'. For example, if we wanted to filter out all files
which are not included as split rules we can define the following element, ``filter-misc.bst``:

.. code:: yaml

   kind: filter

   # Declare the sole build-dependency of the filter element
   build-depends:
   - import.bst

   # Filter out all files which are not declared as split rules
   config:
     exclude:
     - foo
     - bar
     include-orphans: True

The artifact of ``filter-misc.bst`` will only contain the file 'baz'.

Below is more information regarding the the default configurations and possible options
of the filter element:

.. literalinclude:: ../../../src/buildstream/plugins/elements/filter.yaml
   :language: yaml
"""

from buildstream import Element, ElementError, Scope


class FilterElement(Element):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    BST_ARTIFACT_VERSION = 1

    # The filter element's output is its dependencies, so
    # we must rebuild if the dependencies change even when
    # not in strict build plans.
    BST_STRICT_REBUILD = True

    # This element ignores sources, so we should forbid them from being
    # added, to reduce the potential for confusion
    BST_FORBID_SOURCES = True

    # Filter elements do not run any commands
    BST_RUN_COMMANDS = False

    def configure(self, node):
        node.validate_keys(["include", "exclude", "include-orphans", "pass-integration"])

        self.include_node = node.get_sequence("include")
        self.exclude_node = node.get_sequence("exclude")

        self.include = self.include_node.as_str_list()
        self.exclude = self.exclude_node.as_str_list()
        self.include_orphans = node.get_bool("include-orphans")
        self.pass_integration = node.get_bool("pass-integration", False)

    def preflight(self):
        # Exactly one build-depend is permitted
        build_deps = list(self.dependencies(Scope.BUILD, recurse=False))
        if len(build_deps) != 1:
            detail = "Full list of build-depends:\n"
            deps_list = "  \n".join([x.name for x in build_deps])
            detail += deps_list
            raise ElementError(
                "{}: {} element must have exactly 1 build-dependency, actually have {}".format(
                    self, type(self).__name__, len(build_deps)
                ),
                detail=detail,
                reason="filter-bdepend-wrong-count",
            )

        # That build-depend must not also be a runtime-depend
        runtime_deps = list(self.dependencies(Scope.RUN, recurse=False))
        if build_deps[0] in runtime_deps:
            detail = "Full list of runtime depends:\n"
            deps_list = "  \n".join([x.name for x in runtime_deps])
            detail += deps_list
            raise ElementError(
                "{}: {} element's build dependency must not also be a runtime dependency".format(
                    self, type(self).__name__
                ),
                detail=detail,
                reason="filter-bdepend-also-rdepend",
            )

        # If a parent does not produce an artifact, fail and inform user that the dependency
        # must produce artifacts
        if not build_deps[0].BST_ELEMENT_HAS_ARTIFACT:
            detail = "{} does not produce an artifact, so there is nothing to filter".format(build_deps[0].name)
            raise ElementError(
                "{}: {} element's build dependency must produce an artifact".format(self, type(self).__name__),
                detail=detail,
                reason="filter-bdepend-no-artifact",
            )

    def get_unique_key(self):
        key = {
            "include": sorted(self.include),
            "exclude": sorted(self.exclude),
            "orphans": self.include_orphans,
        }
        return key

    def configure_sandbox(self, sandbox):
        pass

    def stage(self, sandbox):
        pass

    def assemble(self, sandbox):
        with self.timed_activity("Staging artifact", silent_nested=True):
            for dep in self.dependencies(Scope.BUILD, recurse=False):
                # Check that all the included/excluded domains exist
                pub_data = dep.get_public_data("bst")
                split_rules = pub_data.get_mapping("split-rules", {})
                unfound_includes = []
                for domain in self.include:
                    if domain not in split_rules:
                        unfound_includes.append(domain)
                unfound_excludes = []
                for domain in self.exclude:
                    if domain not in split_rules:
                        unfound_excludes.append(domain)

                detail = []
                if unfound_includes:
                    detail.append("Unknown domains were used in {}".format(self.include_node.get_provenance()))
                    detail.extend([" - {}".format(domain) for domain in unfound_includes])

                if unfound_excludes:
                    detail.append("Unknown domains were used in {}".format(self.exclude_node.get_provenance()))
                    detail.extend([" - {}".format(domain) for domain in unfound_excludes])

                if detail:
                    detail = "\n".join(detail)
                    raise ElementError("Unknown domains declared.", detail=detail)

                dep.stage_artifact(sandbox, include=self.include, exclude=self.exclude, orphans=self.include_orphans)
        return ""

    def _get_source_element(self):
        # Filter elements act as proxies for their sole build-dependency
        build_deps = list(self.dependencies(Scope.BUILD, recurse=False))
        assert len(build_deps) == 1
        output_elm = build_deps[0]._get_source_element()
        return output_elm

    def integrate(self, sandbox):
        if self.pass_integration:
            for dep in self.dependencies(Scope.BUILD, recurse=False):
                dep.integrate(sandbox)
        super().integrate(sandbox)


def setup():
    return FilterElement
