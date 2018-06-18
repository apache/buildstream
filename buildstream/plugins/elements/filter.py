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
This filters another element by producing an output that is a subset of
the filtered element.

To specify the element to filter, specify it as the one and only build
dependency to filter. See :ref:`Dependencies <format_dependencies>`
for what dependencies are and how to specify them.

Dependencies aside from the filtered element may be specified, but
they must be runtime dependencies only. This can be useful to propagate
runtime dependencies forward from this filter element onto its reverse
dependencies.

When workspaces are opened, closed or reset on this element, or this
element is tracked, instead of erroring due to a lack of sources, this
element will transparently pass on the command to its sole build-dependency.

The default configuration and possible options are as such:
  .. literalinclude:: ../../../buildstream/plugins/elements/filter.yaml
     :language: yaml
"""

from buildstream import Element, ElementError, Scope


class FilterElement(Element):
    # pylint: disable=attribute-defined-outside-init

    # The filter element's output is it's dependencies, so
    # we must rebuild if the dependencies change even when
    # not in strict build plans.
    BST_STRICT_REBUILD = True

    # This element ignores sources, so we should forbid them from being
    # added, to reduce the potential for confusion
    BST_FORBID_SOURCES = True

    def configure(self, node):
        self.node_validate(node, [
            'include', 'exclude', 'include-orphans'
        ])

        self.include = self.node_get_member(node, list, 'include')
        self.exclude = self.node_get_member(node, list, 'exclude')
        self.include_orphans = self.node_get_member(node, bool, 'include-orphans')

    def preflight(self):
        # Exactly one build-depend is permitted
        build_deps = list(self.dependencies(Scope.BUILD, recurse=False))
        if len(build_deps) != 1:
            detail = "Full list of build-depends:\n"
            deps_list = "  \n".join([x.name for x in build_deps])
            detail += deps_list
            raise ElementError("{}: {} element must have exactly 1 build-dependency, actually have {}"
                               .format(self, type(self).__name__, len(build_deps)),
                               detail=detail, reason="filter-bdepend-wrong-count")

        # That build-depend must not also be a runtime-depend
        runtime_deps = list(self.dependencies(Scope.RUN, recurse=False))
        if build_deps[0] in runtime_deps:
            detail = "Full list of runtime depends:\n"
            deps_list = "  \n".join([x.name for x in runtime_deps])
            detail += deps_list
            raise ElementError("{}: {} element's build dependency must not also be a runtime dependency"
                               .format(self, type(self).__name__),
                               detail=detail, reason="filter-bdepend-also-rdepend")

    def get_unique_key(self):
        key = {
            'include': sorted(self.include),
            'exclude': sorted(self.exclude),
            'orphans': self.include_orphans,
        }
        return key

    def configure_sandbox(self, sandbox):
        pass

    def stage(self, sandbox):
        pass

    def assemble(self, sandbox):
        with self.timed_activity("Staging artifact", silent_nested=True):
            for dep in self.dependencies(Scope.BUILD):
                dep.stage_artifact(sandbox, include=self.include,
                                   exclude=self.exclude, orphans=self.include_orphans)
        return ""

    def _get_source_element(self):
        # Filter elements act as proxies for their sole build-dependency
        build_deps = list(self.dependencies(Scope.BUILD, recurse=False))
        assert len(build_deps) == 1
        output_elm = build_deps[0]._get_source_element()
        return output_elm


def setup():
    return FilterElement
