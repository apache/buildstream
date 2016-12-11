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

import sys

try:
    from setuptools import setup, find_packages
except ImportError:
    print("BuildStream requires setuptools in order to build. Install it using"
          " your package manager (usually python3-setuptools) or via pip (pip3"
          " install setuptools).")
    sys.exit(1)

try:
    import gi
except ImportError:
    print("BuildStream requires PyGObject (aka PyGI). Install it using"
          " your package manager (usually pygobject3 or python-gi).")
    sys.exit(1)

try:
    gi.require_version('OSTree', '1.0')
    from gi.repository import OSTree
except:
    print("BuildStream requires OSTree with Python bindings. Install it using"
          " your package manager (usually ostree or gir1.2-ostree-1.0).")
    sys.exit(1)

setup(name='buildstream',
      version='0.1',
      description='A framework for modelling build pipelines in YAML',
      license='LGPL',
      packages=find_packages(),
      package_data={'buildstream': ['plugins/*/*.py', 'data/*.yaml']},
      scripts=['bin/build-stream'],
      install_requires=[
          'ruamel.yaml',
          'pluginbase',
          'argparse'
      ],
      setup_requires=['pytest-runner'],
      tests_require=['pep8',
                     'coverage',
                     'pytest-datafiles',
                     'pytest-pep8',
                     'pytest-cov',
                     'pytest'],
      zip_safe=False)
