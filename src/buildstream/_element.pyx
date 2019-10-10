#
#  Copyright (C) 2018 Bloomberg Finance LP
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library. If not, see <http://www.gnu.org/licenses/>.
#
from .node cimport MappingNode, Node, ScalarNode, SequenceNode
from .sandbox._config import SandboxConfig
from ._platform import Platform
from ._variables cimport Variables


# Expand the splits in the public data using the Variables in the element
def expand_splits(MappingNode element_public not None, Variables variables not None):
    cdef MappingNode element_bst = element_public.get_mapping('bst', default={})
    cdef MappingNode element_splits = element_bst.get_mapping('split-rules', default={})

    cdef str domain
    cdef list new_splits
    cdef SequenceNode splits
    cdef ScalarNode split

    if element_splits:
        # Resolve any variables in the public split rules directly
        for domain, splits in element_splits.items():
            for split in splits:
                split.value = variables.subst(split.as_str())
    else:
        element_public['split-rules'] = {}

    return element_public


# Sandbox-specific configuration data, to be passed to the sandbox's constructor.
#
def extract_sandbox_config(object context, object project, object meta, MappingNode defaults):
    cdef MappingNode sandbox_config

    if meta.is_junction:
        sandbox_config = Node.from_dict(
            Node,
            {
                'build-uid': 0,
                'build-gid': 0
            },
        )
    else:
        sandbox_config = (<MappingNode> project._sandbox).clone()

    # The default config is already composited with the project overrides
    cdef MappingNode sandbox_defaults = defaults.get_mapping('sandbox', default={})
    sandbox_defaults = sandbox_defaults.clone()

    sandbox_defaults._composite(sandbox_config)
    (<MappingNode> meta.sandbox)._composite(sandbox_config)
    sandbox_config._assert_fully_composited()

    # Sandbox config, unlike others, has fixed members so we should validate them
    sandbox_config.validate_keys(['build-uid', 'build-gid', 'build-os', 'build-arch'])

    cdef str build_arch = sandbox_config.get_str('build-arch', default=None)
    if build_arch:
        build_arch = Platform.canonicalize_arch(build_arch)
    else:
        build_arch = context.platform.get_host_arch()

    build_os = sandbox_config.get_str('build-arch', default=None)
    if not build_os:
        build_os = context.platform.get_host_os()

    return SandboxConfig(
        sandbox_config.get_int('build-uid'),
        sandbox_config.get_int('build-gid'),
        sandbox_config.get_str('build-os', default=build_os),
        build_arch)
