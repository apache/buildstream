#
#  Copyright 2018 Bloomberg Finance LP
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
#  Authors:
#        Chandan Singh <csingh43@bloomberg.net>

"""
pip - stage python packages using pip
=====================================

**Host depndencies:**

  * ``pip`` python module

This plugin will download source distributions for specified packages using
``pip`` but will not install them. It is expected that the elements using this
source will install the downloaded packages.

Downloaded tarballs will be stored in a directory called ".bst_pip_downloads".

**Usage:**

.. code:: yaml

   # Specify the pip source kind
   kind: pip

   # Optionally specify index url, defaults to PyPi
   # This url is used to discover new versions of packages and download them
   # Projects intending to mirror their sources to a permanent location should
   # use an aliased url, and declare the alias in the project configuration
   url: https://mypypi.example.com/simple

   # Optionally specify the path to requirements files
   # Note that either 'requirements-files' or 'packages' must be defined
   requirements-files:
   - requirements.txt

   # Optionally specify a list of additional packages
   # Note that either 'requirements-files' or 'packages' must be defined
   packages:
   - flake8

   # Specify the ref. It is a list of strings of format
   # "<package-name>==<version>", separated by "\\n".
   # Usually this will be contents of a requirements.txt file where all
   # package versions have been frozen.
   ref: "flake8==3.5.0\\nmccabe==0.6.1\\npkg-resources==0.0.0\\npycodestyle==2.3.1\\npyflakes==1.6.0"

See :ref:`built-in functionality doumentation <core_source_builtins>` for
details on common configuration options for sources.
"""

import hashlib
import os
import re

from buildstream import Source, SourceError, utils

_OUTPUT_DIRNAME = ".bst_pip_downloads"
_PYPI_INDEX_URL = "https://pypi.org/simple/"

# Used only for finding pip command
_PYTHON_VERSIONS = [
    "python",  # when running in a venv, we might not have the exact version
    "python2.7",
    "python3.0",
    "python3.1",
    "python3.2",
    "python3.3",
    "python3.4",
    "python3.5",
    "python3.6",
    "python3.7",
    "python3.8",
]

# List of allowed extensions taken from
# https://docs.python.org/3/distutils/sourcedist.html.
# Names of source distribution archives must be of the form
# '%{package-name}-%{version}.%{extension}'.
_SDIST_RE = re.compile(r"^([\w.-]+?)-((?:[\d.]+){2,})\.(?:tar|tar.bz2|tar.gz|tar.xz|tar.Z|zip)$", re.IGNORECASE)


class PipSource(Source):
    # pylint: disable=attribute-defined-outside-init

    BST_MIN_VERSION = "2.0"

    # We need access to previous sources at track time to use requirements.txt
    # but not at fetch time as self.ref should contain sufficient information
    # for this plugin
    BST_REQUIRES_PREVIOUS_SOURCES_TRACK = True

    def configure(self, node):
        node.validate_keys(["url", "packages", "ref", "requirements-files"] + Source.COMMON_CONFIG_KEYS)
        self.ref = node.get_str("ref", None)
        self.original_url = node.get_str("url", _PYPI_INDEX_URL)
        self.index_url = self.translate_url(self.original_url)
        self.packages = node.get_str_list("packages", [])
        self.requirements_files = node.get_str_list("requirements-files", [])

        if not (self.packages or self.requirements_files):
            raise SourceError("{}: Either 'packages' or 'requirements-files' must be specified".format(self))

    def preflight(self):
        # Try to find a pip version that spports download command
        self.host_pip = None
        for python in reversed(_PYTHON_VERSIONS):
            try:
                host_python = utils.get_host_tool(python)
                rc = self.call([host_python, "-m", "pip", "download", "--help"])
                if rc == 0:
                    self.host_pip = [host_python, "-m", "pip"]
                    break
            except utils.ProgramNotFoundError:
                pass

        if self.host_pip is None:
            raise SourceError("{}: Unable to find a suitable pip command".format(self))

    def get_unique_key(self):
        return [self.original_url, self.ref]

    def is_cached(self):
        return os.path.exists(self._mirror) and os.listdir(self._mirror)

    def get_ref(self):
        return self.ref

    def load_ref(self, node):
        self.ref = node.get_str("ref", None)

    def set_ref(self, ref, node):
        node["ref"] = self.ref = ref

    def track(self, previous_sources_dir):  # pylint: disable=arguments-differ
        # XXX pip does not offer any public API other than the CLI tool so it
        # is not feasible to correctly parse the requirements file or to check
        # which package versions pip is going to install.
        # See https://pip.pypa.io/en/stable/user_guide/#using-pip-from-your-program
        # for details.
        # As a result, we have to wastefully install the packages during track.
        with self.tempdir() as tmpdir:
            install_args = self.host_pip + [
                "download",
                "--no-binary",
                ":all:",
                "--index-url",
                self.index_url,
                "--dest",
                tmpdir,
            ]
            for requirement_file in self.requirements_files:
                fpath = os.path.join(previous_sources_dir, requirement_file)
                install_args += ["-r", fpath]
            install_args += self.packages

            self.call(install_args, fail="Failed to install python packages")
            reqs = self._parse_sdist_names(tmpdir)

        return "\n".join(["{}=={}".format(pkg, ver) for pkg, ver in reqs])

    def fetch(self):  # pylint: disable=arguments-differ
        with self.tempdir() as tmpdir:
            packages = self.ref.strip().split("\n")
            package_dir = os.path.join(tmpdir, "packages")
            os.makedirs(package_dir)
            self.call(
                [
                    *self.host_pip,
                    "download",
                    "--no-binary",
                    ":all:",
                    "--index-url",
                    self.index_url,
                    "--dest",
                    package_dir,
                    *packages,
                ],
                fail="Failed to install python packages: {}".format(packages),
            )

            # If the mirror directory already exists, assume that some other
            # process has fetched the sources before us and ensure that we do
            # not raise an error in that case.
            try:
                utils.move_atomic(package_dir, self._mirror)
            except utils.DirectoryExistsError:
                # Another process has beaten us and has fetched the sources
                # before us.
                pass
            except OSError as e:
                raise SourceError(
                    "{}: Failed to move downloaded pip packages from '{}' to '{}': {}".format(
                        self, package_dir, self._mirror, e
                    )
                ) from e

    def stage(self, directory):
        with self.timed_activity("Staging Python packages", silent_nested=True):
            utils.copy_files(self._mirror, os.path.join(directory, _OUTPUT_DIRNAME))

    # Directory where this source should stage its files
    #
    @property
    def _mirror(self):
        if not self.ref:
            return None
        return os.path.join(
            self.get_mirror_directory(),
            utils.url_directory_name(self.original_url),
            hashlib.sha256(self.ref.encode()).hexdigest(),
        )

    # Parse names of downloaded source distributions
    #
    # Args:
    #    basedir (str): Directory containing source distribution archives
    #
    # Returns:
    #    (list): List of (package_name, version) tuples in sorted order
    #
    def _parse_sdist_names(self, basedir):
        reqs = []
        for f in os.listdir(basedir):
            pkg = _match_package_name(f)
            if pkg is not None:
                reqs.append(pkg)

        return sorted(reqs)


# Extract the package name and version of a source distribution
#
# Args:
#    filename (str): Filename of the source distribution
#
# Returns:
#    (tuple): A tuple of (package_name, version)
#
def _match_package_name(filename):
    pkg_match = _SDIST_RE.match(filename)
    if pkg_match is None:
        return None
    return pkg_match.groups()


def setup():
    return PipSource
