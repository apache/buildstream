#!/usr/bin/env python3
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

from setuptools import setup, find_packages

setup(
    name="sample-plugins",
    version="1.2.3",
    description="A collection of sample plugins for testing.",
    license="LGPL",
    url="https://example.com/sample-plugins",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,
    entry_points={
        "buildstream.plugins.elements": ["sample = sample_plugins.elements.sample",],
        "buildstream.plugins.sources": ["sample = sample_plugins.sources.sample",],
    },
    zip_safe=False,
)
# eof setup()
