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
from .node cimport MappingNode, ScalarNode, SequenceNode
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
