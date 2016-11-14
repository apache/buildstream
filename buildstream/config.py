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

import os

#
# Some information about where we are installed
#
_site_info = {}

# The package root, wherever we are running the package from
_site_info['root']             = os.path.dirname(os.path.abspath(__file__))

# The Element plugin directory
_site_info['element_plugins']  = os.path.join (_site_info['root'], 'plugins', 'elements')

# The Source plugin directory
_site_info['source_plugins']   = os.path.join (_site_info['root'], 'plugins', 'sources')

# Default user configuration
_site_info['default_config']   = os.path.join (_site_info['root'], 'data', 'default.yaml')
