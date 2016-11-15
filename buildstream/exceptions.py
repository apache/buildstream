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

class PluginError(Exception):
    """Raised on plugin related errors.

    This exception is raised when a plugin was not loaded correctly,
    or when the appropriate plugin could not be found to implement
    a given :class:`.Source` or :class:`.Element`
    """
    pass

class LoadError(Exception):
    """Raised while loading some YAML.

    This exception is raised when loading or parsing YAML.
    """
    pass
