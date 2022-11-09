#!/usr/bin/env python3
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
#  Authors:
#        Tristan Van Berkom <tristan.vanberkom@codethink.co.uk>
#        Benjamin Schubert <bschubert15@bloomberg.net>

import os
from pathlib import Path
import re
import sys

import packaging.version


###################################
# Ensure we have a version number #
###################################

# Add local directory to the path, in order to be able to import versioneer
sys.path.append(os.path.dirname(__file__))
import versioneer  # pylint: disable=wrong-import-position


def mark_unstable_version(version_string):
    # When publishing to PyPI we must be sure that unstable releases are
    # marked as such, so `pip install` doesn't install them by default.

    v = packaging.version.parse(version_string)

    # BuildStream version scheme: if MINOR version is odd, then
    # this is an unstable release.
    is_unstable_release = v.minor % 2 != 0

    # Python PEP440 version scheme: use an explicit postfix to mark development
    # and prereleases.
    if is_unstable_release:
        if v.local or v.is_devrelease or v.is_prerelease:
            # PyPI will ignore these without us marking them.
            return version_string
        else:
            return version_string + ".dev0"

    return version_string


# Extend versioneer to support our custom version style.
_render = versioneer.render


def render_version(pieces, style):
    if style == "pep440_buildstream":
        result = _render(pieces, "pep440")
        result["version"] = mark_unstable_version(result["version"])
    else:
        result = _render(pieces, style)
    return result


versioneer.render = render_version

version = versioneer.get_version()

if version.startswith("0+untagged"):
    print(
        "Your git repository has no tags - BuildStream can't determine its version. Please run `git fetch --tags`.",
        file=sys.stderr,
    )
    sys.exit(1)


##################################################################
# Python requirements
##################################################################
REQUIRED_PYTHON_MAJOR = 3
REQUIRED_PYTHON_MINOR = 7

if sys.version_info[0] != REQUIRED_PYTHON_MAJOR or sys.version_info[1] < REQUIRED_PYTHON_MINOR:
    print("BuildStream requires Python >= 3.7")
    sys.exit(1)

try:
    from setuptools import setup, find_packages, Command, Extension
    from setuptools.command.easy_install import ScriptWriter
except ImportError:
    print(
        "BuildStream requires setuptools in order to build. Install it using"
        " your package manager (usually python3-setuptools) or via pip (pip3"
        " install setuptools)."
    )
    sys.exit(1)


############################################################
# List the BuildBox binaries to ship in the wheel packages #
############################################################
#
# BuildBox isn't widely available in OS distributions. To enable a "one click"
# install for BuildStream, we bundle prebuilt BuildBox binaries in our binary
# wheel packages.
#
# The binaries are provided by the buildbox-integration Gitlab project:
# https://gitlab.com/BuildGrid/buildbox/buildbox-integration
#
# If you want to build a wheel with the BuildBox binaries included, set the
# env var "BST_BUNDLE_BUILDBOX=1" when running setup.py.

try:
    BUNDLE_BUILDBOX = int(os.environ.get("BST_BUNDLE_BUILDBOX", "0"))
except ValueError:
    print("BST_BUNDLE_BUILDBOX must be an integer. Please set it to '1' to enable, '0' to disable", file=sys.stderr)
    raise SystemExit(1)


def list_buildbox_binaries():
    expected_binaries = [
        "buildbox-casd",
        "buildbox-fuse",
        "buildbox-run",
    ]

    if BUNDLE_BUILDBOX:
        bst_package_dir = Path(__file__).parent.joinpath("src/buildstream")
        buildbox_dir = bst_package_dir.joinpath("subprojects", "buildbox")
        buildbox_binaries = [buildbox_dir.joinpath(name) for name in expected_binaries]

        missing_binaries = [path for path in buildbox_binaries if not path.is_file()]
        if missing_binaries:
            paths_text = "\n".join(["  * {}".format(path) for path in missing_binaries])
            print(
                "Expected BuildBox binaries were not found. "
                "Set BST_BUNDLE_BUILDBOX=0 or provide:\n\n"
                "{}\n".format(paths_text),
                file=sys.stderr,
            )
            raise SystemExit(1)

        for path in buildbox_binaries:
            if path.is_symlink():
                print(
                    "Bundled BuildBox binaries must not be symlinks. Please fix {}".format(path),
                    file=sys.stderr,
                )
                raise SystemExit(1)

        return [str(path.relative_to(bst_package_dir)) for path in buildbox_binaries]
    else:
        return []


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
    man_dir = os.path.join(bst_dir, "man")
    try:
        man_pages = os.listdir(man_dir)
        return [os.path.join("man", page) for page in man_pages]
    except FileNotFoundError:
        # Do not error out when 'man' directory does not exist
        return []


######################################################
# List the data files needed by buildstream._testing #
######################################################
#
# List the datafiles which need to be installed for the
# buildstream._testing package
#
def list_testing_datafiles():
    bst_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    data_dir = bst_dir.joinpath("src", "buildstream", "_testing", "_sourcetests", "project")
    return [str(f) for f in data_dir.rglob("*")]


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
#
# This also sets an environment variable to disable gRPC fork support as it
# can cause problems in certain environments and BuildStream doesn't need it.
TEMPLATE = """\
# -*- coding: utf-8 -*-
import os
import sys

from {0} import {1}

if __name__ == '__main__':
    os.environ['GRPC_ENABLE_FORK_SUPPORT'] = '0'
    sys.exit({2}())"""


# Modify the get_args() function of the ScriptWriter class
# Note: the pylint no-member warning has been disabled as the functions: get_header(),
# ensure_safe_name() and _get_script_args() are all members of this class.
# pylint: disable=no-member
@classmethod
def get_args(cls, dist, header=None):
    if header is None:
        header = cls.get_header()
    for name, ep in dist.get_entry_map("console_scripts").items():
        cls._ensure_safe_name(name)
        script_text = TEMPLATE.format(ep.module_name, ep.attrs[0], ".".join(ep.attrs))
        args = cls._get_script_args("console", name, header, script_text)
        for res in args:
            yield res


ScriptWriter.get_args = get_args


#####################################################
#         gRPC command for code generation          #
#####################################################
class BuildGRPC(Command):
    """Command to generate project *_pb2.py modules from proto files."""

    description = "build gRPC protobuf modules"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        try:
            import grpc_tools.command
        except ImportError:
            print(
                "BuildStream requires grpc_tools in order to build gRPC modules.\n"
                "Install it via pip (pip3 install grpcio-tools)."
            )
            sys.exit(1)

        protos_root = "src/buildstream/_protos"

        grpc_tools.command.build_package_protos(protos_root)

        # Postprocess imports in generated code
        for root, _, files in os.walk(protos_root):
            for filename in files:
                if filename.endswith(".py"):
                    path = os.path.join(root, filename)
                    with open(path, "r", encoding="utf-8") as f:
                        code = f.read()

                    # All protos are in buildstream._protos
                    code = re.sub(r"^from ", r"from buildstream._protos.", code, flags=re.MULTILINE)
                    # Except for the core google.protobuf protos
                    code = re.sub(
                        r"^from buildstream._protos.google.protobuf", r"from google.protobuf", code, flags=re.MULTILINE
                    )

                    with open(path, "w", encoding="utf-8") as f:
                        f.write(code)


def get_cmdclass():
    cmdclass = {
        "build_grpc": BuildGRPC,
    }
    cmdclass.update(versioneer.get_cmdclass())
    return cmdclass


#####################################################
#               Gather requirements                 #
#####################################################
with open("requirements/requirements.in", encoding="utf-8") as install_reqs:
    install_requires = install_reqs.read().splitlines()

#####################################################
#     Prepare package description from README       #
#####################################################
with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "README.rst"), encoding="utf-8") as readme:
    long_description = readme.read()


#####################################################
#            Setup Cython and extensions            #
#####################################################
# We want to ensure that source distributions always
# include the .c files, in order to allow users to
# not need cython when building.
def assert_cython_required():
    if "sdist" not in sys.argv:
        return

    print(
        "Cython is required when building 'sdist' in order to "
        "ensure source distributions can be built without Cython. "
        "Please install it using your package manager (usually 'python3-cython') "
        "or pip (pip install cython).",
        file=sys.stderr,
    )

    raise SystemExit(1)


try:
    ENABLE_CYTHON_TRACE = int(os.environ.get("BST_CYTHON_TRACE", "0"))
except ValueError:
    print("BST_CYTHON_TRACE must be an integer. Please set it to '1' to enable, '0' to disable", file=sys.stderr)
    raise SystemExit(1)


extension_macros = [("CYTHON_TRACE", ENABLE_CYTHON_TRACE)]


def cythonize(extensions, **kwargs):
    try:
        from Cython.Build import cythonize as _cythonize
    except ImportError:
        assert_cython_required()

        print("Cython not found. Using preprocessed c files instead")

        missing_c_sources = []

        for extension in extensions:
            for source in extension.sources:
                if source.endswith(".pyx"):
                    c_file = source.replace(".pyx", ".c")

                    if not os.path.exists(c_file):
                        missing_c_sources.append((extension, c_file))

        if missing_c_sources:
            for extension, source in missing_c_sources:
                print("Missing '{}' for building extension '{}'".format(source, extension.name))

            raise SystemExit(1)
        return extensions

    return _cythonize(extensions, **kwargs)


def register_cython_module(module_name, dependencies=None):
    def files_from_module(modname):
        basename = "src/{}".format(modname.replace(".", "/"))
        return "{}.pyx".format(basename), "{}.pxd".format(basename)

    if dependencies is None:
        dependencies = []

    implementation_file, definition_file = files_from_module(module_name)

    assert os.path.exists(implementation_file)

    depends = []
    if os.path.exists(definition_file):
        depends.append(definition_file)

    for module in dependencies:
        imp_file, def_file = files_from_module(module)
        assert os.path.exists(imp_file), "Dependency file not found: {}".format(imp_file)
        assert os.path.exists(def_file), "Dependency declaration file not found: {}".format(def_file)

        depends.append(imp_file)
        depends.append(def_file)

    BUILD_EXTENSIONS.append(
        Extension(
            name=module_name,
            sources=[implementation_file],
            depends=depends,
            define_macros=extension_macros,
        )
    )


BUILD_EXTENSIONS = []

register_cython_module("buildstream.node")
register_cython_module("buildstream._loader.loadelement", dependencies=["buildstream.node"])
register_cython_module("buildstream._yaml", dependencies=["buildstream.node"])
register_cython_module("buildstream._types")
register_cython_module("buildstream._utils")
register_cython_module("buildstream._variables", dependencies=["buildstream.node"])

#####################################################
#             Main setup() Invocation               #
#####################################################
setup(
    name="BuildStream",
    version=version,
    cmdclass=get_cmdclass(),
    author="The Apache Software Foundation",
    author_email="dev@buildstream.apache.org",
    classifiers=[
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Software Development :: Build Tools",
    ],
    description="A framework for modelling build pipelines in YAML",
    license="Apache License Version 2.0",
    long_description=long_description,
    long_description_content_type="text/x-rst; charset=UTF-8",
    url="https://buildstream.build",
    project_urls={
        "Source": "https://github.com/apache/buildstream",
        "Documentation": "https://docs.buildstream.build",
        "Tracker": "https://github.com/apache/buildstream/issues",
        "Mailing List": "https://lists.apache.org/list.html?dev@buildstream.apache.org",
    },
    python_requires="~={}.{}".format(REQUIRED_PYTHON_MAJOR, REQUIRED_PYTHON_MINOR),
    package_dir={"": "src"},
    packages=find_packages(where="src", exclude=("subprojects", "tests", "tests.*")),
    package_data={
        "buildstream": [
            "py.typed",
            "plugins/*/*.py",
            "plugins/*/*.yaml",
            "data/*.yaml",
            "data/*.sh.in",
            *list_buildbox_binaries(),
            *list_testing_datafiles(),
        ]
    },
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
        ("share/man/man1", list_man_pages()),
        ("share/bash-completion/completions", [os.path.join("src", "buildstream", "data", "bst")]),
    ],
    install_requires=install_requires,
    entry_points={"console_scripts": ["bst = buildstream._frontend:cli"]},
    ext_modules=cythonize(
        BUILD_EXTENSIONS,
        compiler_directives={
            # Version of python to use
            # https://cython.readthedocs.io/en/latest/src/userguide/source_files_and_compilation.html#arguments
            "language_level": "3",
            # Enable line tracing when requested only, this is needed in order to generate coverage.
            "linetrace": bool(ENABLE_CYTHON_TRACE),
            "profile": os.environ.get("BST_CYTHON_PROFILE", False),
        },
    ),
    zip_safe=False,
)
