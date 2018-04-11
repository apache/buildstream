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
import subprocess
import sys

if sys.version_info[0] != 3 or sys.version_info[1] < 4:
    print("BuildStream requires Python >= 3.4")
    sys.exit(1)

try:
    from setuptools import setup, find_packages
    from setuptools.command.easy_install import ScriptWriter
except ImportError:
    print("BuildStream requires setuptools in order to build. Install it using"
          " your package manager (usually python3-setuptools) or via pip (pip3"
          " install setuptools).")
    sys.exit(1)


##################################################################
# Bubblewrap requirements
##################################################################
REQUIRED_BWRAP_MAJOR = 0
REQUIRED_BWRAP_MINOR = 1
REQUIRED_BWRAP_PATCH = 2


def exit_bwrap(reason):
    print(reason +
          "\nBuildStream requires Bubblewrap (bwrap) for"
          " sandboxing the build environment. Install it using your package manager"
          " (usually bwrap or bubblewrap)")
    sys.exit(1)


def bwrap_too_old(major, minor, patch):
    if major < REQUIRED_BWRAP_MAJOR:
        return True
    elif major == REQUIRED_BWRAP_MAJOR:
        if minor < REQUIRED_BWRAP_MINOR:
            return True
        elif minor == REQUIRED_BWRAP_MINOR:
            return patch < REQUIRED_BWRAP_PATCH
        else:
            return False
    else:
        return False


def assert_bwrap():
    platform = os.environ.get('BST_FORCE_BACKEND', '') or sys.platform
    if platform.startswith('linux'):
        bwrap_path = shutil.which('bwrap')
        if not bwrap_path:
            exit_bwrap("Bubblewrap not found")

        version_bytes = subprocess.check_output([bwrap_path, "--version"]).split()[1]
        version_string = str(version_bytes, "utf-8")
        major, minor, patch = map(int, version_string.split("."))
        if bwrap_too_old(major, minor, patch):
            exit_bwrap("Bubblewrap too old")


##################################################################
# OSTree version requirements
##################################################################
REQUIRED_OSTREE_YEAR = 2017
REQUIRED_OSTREE_RELEASE = 8


def exit_ostree(reason):
    print(reason +
          "\nBuildStream requires OSTree >= v{}.{} with Python bindings. "
          .format(REQUIRED_OSTREE_YEAR, REQUIRED_OSTREE_RELEASE) +
          "Install it using your package manager (usually ostree or gir1.2-ostree-1.0).")
    sys.exit(1)


def assert_ostree_version():
    platform = os.environ.get('BST_FORCE_BACKEND', '') or sys.platform
    if platform.startswith('linux'):
        try:
            import gi
        except ImportError:
            print("BuildStream requires PyGObject (aka PyGI). Install it using"
                  " your package manager (usually pygobject3 or python-gi).")
            sys.exit(1)

        try:
            gi.require_version('OSTree', '1.0')
            from gi.repository import OSTree
        except ValueError:
            exit_ostree("OSTree not found")

        try:
            if OSTree.YEAR_VERSION < REQUIRED_OSTREE_YEAR or \
               (OSTree.YEAR_VERSION == REQUIRED_OSTREE_YEAR and
                OSTree.RELEASE_VERSION < REQUIRED_OSTREE_RELEASE):
                exit_ostree("OSTree v{}.{} is too old."
                            .format(OSTree.YEAR_VERSION, OSTree.RELEASE_VERSION))
        except AttributeError:
            exit_ostree("OSTree is too old.")


###########################################
# List the pre-built man pages to install #
###########################################
#
# Man pages are automatically generated however it was too difficult
# to integrate with setuptools as a step of the build (FIXME !).
#
# To update the man pages in tree before a release, you need to
# ensure you have the 'click_man' package installed, and run:
#
# python3 setup.py --command-packages=click_man.commands man_pages
#
# Then commit the result.
#
def list_man_pages():
    bst_dir = os.path.dirname(os.path.abspath(__file__))
    man_dir = os.path.join(bst_dir, 'man')
    man_pages = os.listdir(man_dir)
    return [os.path.join('man', page) for page in man_pages]


#####################################################
#                Conditional Checks                 #
#####################################################
#
# Because setuptools... there is no way to pass an option to
# the setup.py explicitly at install time.
#
# So screw it, lets just use an env var.
bst_install_entry_points = {
    'console_scripts': [
        'bst-artifact-receive = buildstream._artifactcache.pushreceive:receive_main'
    ],
}

if not os.environ.get('BST_ARTIFACTS_ONLY', ''):
    assert_bwrap()
    assert_ostree_version()
    bst_install_entry_points['console_scripts'] += [
        'bst = buildstream._frontend:cli'
    ]

_version_template = """\
# coding: utf-8
# file generated by setuptools_scm
# don't change, don't track in version control
__version__ = {version!r}
"""

#####################################################
#    Monkey-patching setuptools for performance     #
#####################################################
#
# The template of easy_install.ScriptWriter is inefficient in our case as it
# imports pkg_resources. Patching the template only doesn't work because of the
# old string formatting used (%). This forces us to overwrite the class function
# as well.
#
# The patch was inspired from https://github.com/ninjaaron/fast-entry_points
# which we believe was also inspired from the code from `setuptools` project.
TEMPLATE = '''\
# -*- coding: utf-8 -*-
import sys

from {0} import {1}

if __name__ == '__main__':
    sys.exit({2}())'''


# Modify the get_args() function of the ScriptWriter class
# Note: the pylint no-member warning has been disabled as the functions: get_header(),
# ensure_safe_name() and _get_script_args() are all members of this class.
# pylint: disable=no-member
@classmethod
def get_args(cls, dist, header=None):
    if header is None:
        header = cls.get_header()
    for name, ep in dist.get_entry_map('console_scripts').items():
        cls._ensure_safe_name(name)
        script_text = TEMPLATE.format(ep.module_name, ep.attrs[0], '.'.join(ep.attrs))
        args = cls._get_script_args('console', name, header, script_text)
        for res in args:
            yield res


ScriptWriter.get_args = get_args


#####################################################
#             Main setup() Invocation               #
#####################################################
setup(name='BuildStream',
      description='A framework for modelling build pipelines in YAML',
      license='LGPL',
      use_scm_version={
          'write_to': "buildstream/__version__.py",
          'write_to_template': _version_template,
      },
      packages=find_packages(),
      package_data={'buildstream': ['plugins/*/*.py', 'plugins/*/*.yaml',
                                    'data/*.yaml', 'data/*.sh.in']},
      data_files=[
          # This is a weak attempt to integrate with the user nicely,
          # installing things outside of the python package itself with pip is
          # not recommended, but there seems to be no standard structure for
          # addressing this; so just installing this here.
          #
          # These do not get installed in developer mode (`pip install --user -e .`)
          #
          # The completions are ignored by bash unless it happens to be installed
          # in the right directory; this is more like a weak statement that we
          # attempt to install bash completion scriptlet.
          #
          ('share/man/man1', list_man_pages()),
          ('share/bash-completion/completions', [
              os.path.join('buildstream', 'data', 'bst')
          ])
      ],
      install_requires=[
          'setuptools',
          'psutil',
          'ruamel.yaml',
          'pluginbase',
          'Click',
          'blessings',
          'jinja2 >= 2.10',
      ],
      entry_points=bst_install_entry_points,
      setup_requires=['pytest-runner', 'setuptools_scm'],
      tests_require=['pep8',
                     # Pin coverage to 4.2 for now, we're experiencing
                     # random crashes with 4.4.2
                     'coverage == 4.4.0',
                     'pytest-datafiles',
                     'pytest-env',
                     'pytest-pep8',
                     'pytest-pylint',
                     'pytest-cov',
                     # Provide option to run tests in parallel, less reliable
                     'pytest-xdist',
                     'pytest >= 3.1.0'],
      zip_safe=False)
