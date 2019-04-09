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
import re
import shutil
import subprocess
import sys
import versioneer


##################################################################
# Python requirements
##################################################################
REQUIRED_PYTHON_MAJOR = 3
REQUIRED_PYTHON_MINOR = 5

if sys.version_info[0] != REQUIRED_PYTHON_MAJOR or sys.version_info[1] < REQUIRED_PYTHON_MINOR:
    print("BuildStream requires Python >= 3.5")
    sys.exit(1)

try:
    from setuptools import setup, find_packages, Command
    from setuptools.command.easy_install import ScriptWriter
    from setuptools.command.test import test as TestCommand
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


def warn_bwrap(reason):
    print(reason +
          "\nBuildStream requires Bubblewrap (bwrap {}.{}.{} or better),"
          " during local builds, for"
          " sandboxing the build environment.\nInstall it using your package manager"
          " (usually bwrap or bubblewrap) otherwise you will be limited to"
          " remote builds only.".format(REQUIRED_BWRAP_MAJOR, REQUIRED_BWRAP_MINOR, REQUIRED_BWRAP_PATCH))


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


def check_for_bwrap():
    platform = os.environ.get('BST_FORCE_BACKEND', '') or sys.platform
    if platform.startswith('linux'):
        bwrap_path = shutil.which('bwrap')
        if not bwrap_path:
            warn_bwrap("Bubblewrap not found")
            return

        version_bytes = subprocess.check_output([bwrap_path, "--version"]).split()[1]
        version_string = str(version_bytes, "utf-8")
        major, minor, patch = map(int, version_string.split("."))
        if bwrap_too_old(major, minor, patch):
            warn_bwrap("Bubblewrap too old")


###########################################
# List the pre-built man pages to install #
###########################################
#
# Man pages are automatically generated however it was too difficult
# to integrate with setuptools as a step of the build (FIXME !).
#
# To update the man pages in tree before a release, run:
#
#     tox -e man
#
# Then commit the result.
#
def list_man_pages():
    bst_dir = os.path.dirname(os.path.abspath(__file__))
    man_dir = os.path.join(bst_dir, 'man')
    try:
        man_pages = os.listdir(man_dir)
        return [os.path.join('man', page) for page in man_pages]
    except FileNotFoundError:
        # Do not error out when 'man' directory does not exist
        return []


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
        'bst-artifact-server = buildstream2._cas.casserver:server_main'
    ],
}

#
# By default BuildStream 2 installs as 'bst2', but allow
# the installer to override this and install as 'bst' if
# they wish
#
bst_entry_point = os.environ.get('BST_ENTRY_POINT', '')
if not bst_entry_point:
    bst_entry_point = 'bst2'

if bst_entry_point not in ('bst', 'bst2'):
    print("BST_ENTRY_POINT was set to '{}'".format(bst_entry_point) +
          ", but only 'bst' or 'bst2' is allowed")
    sys.exit(1)

if not os.environ.get('BST_ARTIFACTS_ONLY', ''):
    check_for_bwrap()
    bst_install_entry_points['console_scripts'] += [
        '{} = buildstream2._frontend:cli'.format(bst_entry_point)
    ]


#####################################################
#       Generate the bash completion scriptlet      #
#####################################################
#
# Generate the bash completion scriptlet as 'bst' or 'bst2'
# depending on the selected entry point name.
#
COMPLETION_SCRIPTLET = """# BuildStream bash completion scriptlet.
#
# On systems which use the bash-completion module for
# completion discovery with bash, this can be installed at:
#
#   pkg-config --variable=completionsdir bash-completion
#
# If BuildStream is not installed system wide, you can
# simply source this script to enable completions or append
# this script to your ~/.bash_completion file.
#
_{entry_point}_completion() {{
    local IFS=$'
'
    COMPREPLY=( $( env COMP_WORDS="${{COMP_WORDS[*]}}" \\
                   COMP_CWORD=$COMP_CWORD \\
                   _BST_COMPLETION=complete $1 ) )
    return 0
}}

complete -F _bst_completion -o nospace {entry_point};
""".format(entry_point=bst_entry_point)


def get_completions_scriptlet():
    bst_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(bst_dir, 'buildstream2', 'data', bst_entry_point)

    # Generate the file on demand, only in response to
    # actually installing.
    with open(path, 'w') as f:
        f.write(COMPLETION_SCRIPTLET)

    # Return the relative path
    return os.path.join('buildstream2', 'data', bst_entry_point)


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
#         gRPC command for code generation          #
#####################################################
class BuildGRPC(Command):
    """Command to generate project *_pb2.py modules from proto files."""

    description = 'build gRPC protobuf modules'
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        try:
            import grpc_tools.command
        except ImportError:
            print("BuildStream requires grpc_tools in order to build gRPC modules.\n"
                  "Install it via pip (pip3 install grpcio-tools).")
            exit(1)

        protos_root = 'buildstream2/_protos'

        grpc_tools.command.build_package_protos(protos_root)

        # Postprocess imports in generated code
        for root, _, files in os.walk(protos_root):
            for filename in files:
                if filename.endswith('.py'):
                    path = os.path.join(root, filename)
                    with open(path, 'r') as f:
                        code = f.read()

                    # All protos are in buildstream._protos
                    code = re.sub(r'^from ', r'from buildstream2._protos.',
                                  code, flags=re.MULTILINE)
                    # Except for the core google.protobuf protos
                    code = re.sub(r'^from buildstream2._protos.google.protobuf', r'from google.protobuf',
                                  code, flags=re.MULTILINE)

                    with open(path, 'w') as f:
                        f.write(code)


#####################################################
#                   Pytest command                  #
#####################################################
class PyTest(TestCommand):
    """Defines a pytest command class to run tests from setup.py"""

    user_options = TestCommand.user_options + [
        ("addopts=", None, "Arguments to pass to pytest"),
        ('index-url=', None, "Specify an index url from which to retrieve "
                             "dependencies"),
    ]

    # pylint: disable=attribute-defined-outside-init
    def initialize_options(self):
        super().initialize_options()
        self.addopts = ""
        self.index_url = None

    def run(self):
        if self.index_url is not None:
            if self.distribution.command_options.get("easy_install") is None:
                self.distribution.command_options["easy_install"] = {}

            self.distribution.command_options["easy_install"]["index_url"] = (
                "cmdline", self.index_url,
            )
        super().run()

    def run_tests(self):
        import shlex
        import pytest

        errno = pytest.main(shlex.split(self.addopts))

        if errno:
            raise SystemExit(errno)


def get_cmdclass():
    cmdclass = {
        'build_grpc': BuildGRPC,
        'pytest': PyTest,
    }
    cmdclass.update(versioneer.get_cmdclass())
    return cmdclass


#####################################################
#               Gather requirements                 #
#####################################################
with open('requirements/dev-requirements.in') as dev_reqs:
    dev_requires = dev_reqs.read().splitlines()

with open('requirements/requirements.in') as install_reqs:
    install_requires = install_reqs.read().splitlines()

#####################################################
#     Prepare package description from README       #
#####################################################
with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                       'README.rst')) as readme:
    long_description = readme.read()


#####################################################
#             Main setup() Invocation               #
#####################################################
setup(name='BuildStream2',
      # Use versioneer
      version=versioneer.get_version(),
      cmdclass=get_cmdclass(),

      author='BuildStream Developers',
      author_email='buildstream-list@gnome.org',
      classifiers=[
          'Environment :: Console',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)',
          'Operating System :: POSIX',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.5',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Topic :: Software Development :: Build Tools'
      ],
      description='A framework for modelling build pipelines in YAML',
      license='LGPL',
      long_description=long_description,
      long_description_content_type='text/x-rst; charset=UTF-8',
      url='https://buildstream.build',
      project_urls={
          'Source': 'https://gitlab.com/BuildStream/buildstream',
          'Documentation': 'https://docs.buildstream.build',
          'Tracker': 'https://gitlab.com/BuildStream/buildstream/issues',
          'Mailing List': 'https://mail.gnome.org/mailman/listinfo/buildstream-list'
      },
      python_requires='~={}.{}'.format(REQUIRED_PYTHON_MAJOR, REQUIRED_PYTHON_MINOR),
      packages=find_packages(exclude=('tests', 'tests.*')),
      package_data={'buildstream2': ['plugins/*/*.py', 'plugins/*/*.yaml',
                                     'data/*.yaml', 'data/*.sh.in']},
      include_package_data=True,
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
              get_completions_scriptlet()
          ])
      ],
      install_requires=install_requires,
      entry_points=bst_install_entry_points,
      tests_require=dev_requires,
      zip_safe=False)
