..
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.



.. _updating_python_deps:

Updating BuildStream's Python dependencies
------------------------------------------
BuildStream's Python dependencies are listed in multiple
`requirements files <https://pip.readthedocs.io/en/latest/reference/pip_install/#requirements-file-format>`_
present in the ``requirements`` directory.

All ``.txt`` files in this directory are generated from the corresponding
``.in`` file, and each ``.in`` file represents a set of dependencies. For
example, ``requirements.in`` contains all runtime dependencies of BuildStream.
``requirements.txt`` is generated from it, and contains pinned versions of all
runtime dependencies (including transitive dependencies) of BuildStream.

When adding a new dependency to BuildStream, or updating existing dependencies,
it is important to update the appropriate requirements file accordingly. After
changing the ``.in`` file, run the following to update the matching ``.txt``
file::

   make -C requirements


Adding support for a new Python release
---------------------------------------
When a new stable release of Python 3 appears, we must explicitly declare
our support for it in the following places.


tox.ini
~~~~~~~
The ``tox.ini`` file defines the environments where the BuildStream test suite
runs.  Every ``py{3.x,3.y}`` list must be updated to contain the new version
number such as ``311`` for CPython 3.11.

Use ``tox -e py311-nocover`` to run the test suite with the new version of
Python.


pyproject.toml
~~~~~~~~~~~~~~


Bump cython version
'''''''''''''''''''
New releases of Cython must be depended on with new versions of Python
in lock step.

When supporting a new Python version, it is important to bump the minimal
dependency on Cython to a new enough version which also supports the new
version of Python.


Wheel details
'''''''''''''
We produce binary "wheel" packages for each supported version of Python.
The cibuildwheel build tool will build for all released versions of Python
so no change is needed in the config.

However, if you want to test wheel building with a prerelease version of Python
you will need to set ``CIBW_PRERELEASE_PYTHONS=1`` in the cibuildwheel
environment.


.github/compose/ci.docker-compose.yml
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Each binary package is tested in a container, using the
`pypa/manylinux <https://github.com/pypa/manylinux>`_ images.

You need to add a new docker-compose service here -- copy the
latest one and update the version number where it appears.


.github/workflows/ci.yml and .github/workflows/release.yml
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
There is a separate CI job to run each of the above tests. Update the
matrix config for the ``test_wheels`` jobs in ``ci.yml`` and ``release.yml``
to add the new Python version.


Removing support for a Python release
-------------------------------------


tox.ini
~~~~~~~
You will need to update the ``py{3.x,3.y}`` lists to remove the old version. In
the ``envlist`` section, make sure the oldest version still has coverage
enabled while the other versions are marked ``-nocover``.


pyproject.toml
~~~~~~~~~~~~~~
The cibuildwheel tool will produce wheels for all versions of Python supported
upstream.. If we drop support for a version before upstream do, update the
``tool.cibuildwheel.skip`` list to skip all platform tags for that version.
The glob ``cp36-*`` would skip all CPython 3.6 builds, for example.


.github/compose/ci.docker-compose.yml
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Remove the corresponding service.


.github/workflows/ci.yml and .github/workflows/release.yml
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Update the matrix config for the `test_wheels` jobs in `ci.yml` and
`release.yml` to remove the old Python version.


ABI compatibility for binary Python packages
--------------------------------------------
The Python binary packages declare system requirements using
`platform compatibility tags <https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/>`_.

For linux-gnu systems we use `manylinux_x_y platform tags <https://peps.python.org/pep-0600/>`_
to specify a minimum GLIBC version. The platform tag is controlled in ``pyproject.toml`` with the
``tool.cibuildwheel.manylinux-x86_64-image`` key.  It must correspond with the version of
GLIBC used in `buildbox-integration <https://gitlab.com/BuildGrid/buildbox/buildbox-integration>`_
to produce static buildbox binaries that are included in the package.
The ``cibuildwheel`` tool uses `auditwheel <https://github.com/pypa/auditwheel>`_
to ensure the correct platform tag is declared.
