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
import shutil
import sys

if sys.version_info[0] != 3 or sys.version_info[1] < 5:
    print("BuildStream requires Python >= 3.5")
    sys.exit(1)

bwrap_path = shutil.which('bwrap')
if not bwrap_path:
    print("Bubblewrap not found: BuildStream requires Bubblewrap (bwrap) for"
          " sandboxing the build environment. Install it using your package manager"
          " (usually bwrap or bubblewrap)")
    sys.exit(1)

try:
    from setuptools import setup, find_packages
except ImportError:
    print("BuildStream requires setuptools in order to build. Install it using"
          " your package manager (usually python3-setuptools) or via pip (pip3"
          " install setuptools).")
    sys.exit(1)


##################################################################
# We require at least v2016.8 of OSTree, which contain the
# fixes in this bug:
#   https://github.com/ostreedev/ostree/pull/417
##################################################################
def exit_ostree(reason):
    print(reason + ": BuildStream requires OSTree >= v2016.8 with Python bindings. "
          "Install it using your package manager (usually ostree or gir1.2-ostree-1.0).")
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
    exit_ostree("OSTree not found")

try:
    checkout_at = OSTree.Repo.checkout_at
except AttributeError:
    exit_ostree("OSTree too old")


setup(name='BuildStream',
      version='0.1',
      description='A framework for modelling build pipelines in YAML',
      license='LGPL',
      packages=find_packages(),
      package_data={'buildstream': ['plugins/*/*.py', 'plugins/*/*.yaml', 'data/*.yaml']},
      install_requires=[
          'setuptools',
          'xdg',
          'psutil',
          'ruamel.yaml',
          'pluginbase',
          'Click',
          'blessings'
      ],
      entry_points='''
      [console_scripts]
      build-stream=buildstream._frontend:cli
      bst=buildstream._frontend:cli
      ''',
      setup_requires=['pytest-runner'],
      tests_require=['pep8',
                     'coverage',
                     'pytest-datafiles',
                     'pytest-pep8',
                     'pytest-cov',
                     'pytest'],
      zip_safe=False)
