#!/usr/bin/env python3
#
#  Copyright (C) 2016 Codethink Limited
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

import collections
import copy

def dictionary_override(dictionary, override):
    """Overrides values in *dictionary* with values from *override*

    This function overrides values in *dictionary* with values from *override*.

    Unlike the dictionary *update()* method, nested values in *override*
    will not obsolete entire subdictionaries in *dictionary*

    This is useful for overriding configuration files and element configurations.

    Args:
       dictionary (dict): A simple dictionary
       override (dict): Another simple dictionary

    Returns:
       A new dictionary which includes the values of both
    """
    result = copy.deepcopy(dictionary)

    for k, v in override.items():
        if isinstance(v, collections.Mapping):
            r = composite_dictionary(result.get(k, {}), v)
            result[k] = r
        else:
            result[k] = override[k]

    return result
