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



.. _porting_project:

Porting the project format
==========================
This document outlines breaking changes made to the project format in BuildStream 2.


The project.conf
----------------
This section outlines breaking changes made to the :ref:`project.conf format <projectconf>`.


Project name
~~~~~~~~~~~~
Various features related to :mod:`junction <elements.junction>` elements have been added
which allow addressing projects by their :ref:`project names <project_format_name>`. For this
reason, it is important to ensure that your project names are appropriately unique.


Project versioning
~~~~~~~~~~~~~~~~~~
Instead of maintaining a separate version number for the format and for BuildStream releases,
projects now declare the minimum version of BuildStream 2 they depend on.

The ``format-version`` attribute should be removed from your project.conf (if present) and
the :ref:`min-version <project_min_version>` attribute must be added.


Some attributes can only be specified in project.conf
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Whenever specifying any of the following toplevel project attributes, they must be
specified inside the project.conf itself and cannot be :ref:`included <format_directives_include>`
from a separate file:

* :ref:`name <project_format_name>`
* :ref:`element-path <project_element_path>`
* :ref:`min-version <project_min_version>`
* :ref:`plugins <project_plugins>`


Artifact cache configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The format for declaring :ref:`artifact caches <project_artifact_cache>` which are associated to
your project have been completely redesigned.

**BuildStream 1:**

.. code:: yaml

   #
   # We used to specify a single URL
   #
   artifacts:
     url: https://foo.com/artifacts

**BuildStream 2:**

.. code:: yaml

   #
   # Now we declare a list, and credentials have been split
   # out into a separate "auth" dictionary
   #
   artifacts:
   - url: https://foo.com:11001
     auth:
       server-cert: server.crt


Loading plugins
~~~~~~~~~~~~~~~
The format for :ref:`loading plugins <project_plugins>` has been completely redesigned.

.. tip::

   A new method for :ref:`loading plugins through junctions <project_plugins_junction>`
   has been added. In the interest of ensuring strong determinism and reliability it is
   strongly recommended to use this new method.


Local plugins
'''''''''''''
Here is an example of how loading :ref:`local plugins <project_plugins_local>` has changed.

**BuildStream 1:**

.. code:: yaml

   plugins:

   - origin: local
     path: plugins/sources

     #
     # We used to specify version numbers, these no longer exist.
     #
     sources:
       mysource: 0

**BuildStream 2:**

.. code:: yaml

   plugins:

   - origin: local
     path: plugins/sources

     #
     # Now we merely specify a list of plugins to load from
     # a given project local directory
     #
     sources:
     - mysource


Pip plugins
'''''''''''
Here is an example of how loading :ref:`pip plugins <project_plugins_pip>` has changed.

**BuildStream 1:**

.. code:: yaml

   plugins:

   - origin: pip

     package-name: vegetables

     #
     # We used to specify version numbers, these no longer exist.
     #
     elements:
       potato: 0

**BuildStream 2:**

.. code:: yaml

   plugins:

   - origin: pip

     #
     # We can now specify version constraints
     #
     package-name: vegetables>=1.2

     #
     # Now we merely specify a list of plugins to load from
     # a given pip package that is expected to be installed
     #
     elements:
     - potato


Core elements
-------------
This section outlines breaking changes made to :ref:`core element plugins <plugins>` which
may require you to make changes to your project.


The :mod:`stack <elements.stack>` element
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stack elements dependencies are now hard required to be both build and runtime dependencies.


The :mod:`script <elements.script>` element
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The ``layout`` attribute has now been removed in favor of dependency level configuration.

Here is an example script which collects a manifest of all files in the hypothetical
``system.bst`` element, using a hypothetical base runtime element ``base-utilities.bst``.

**BuildStream 1:**

.. code:: yaml

   kind: script

   build-depends:
   - base-utilities.bst
   - system.bst

   config:
     #
     # The old format was redundant and required explicit layout
     # of the dependencies already declared above.
     #
     layout:
     - element: base-utilities.bst
       destination: /
     - element: system.bst
       destination: "%{build-root}"

     commands:
     - find %{build-root} > %{install-root}/manifest.log

**BuildStream 2:**

.. code:: yaml

   kind: script

   #
   # The default location is "/" so there is no need to configure
   # the "base-utilities.bst" dependency
   #
   build-depends:
   - base-utilities.bst
   - system.bst
     config:
       location: "%{build-root}"

   config:
     commands:
     - find %{build-root} > %{install-root}/manifest.log

.. tip::

   The ``location`` dependency level configuration is also supported by all
   :mod:`BuildElement <buildstream.buildelement>` plugins.


The :mod:`junction <elements.junction>` element
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The YAML format for declaring junctions has not changed, however the way that
multiple junctions interact in a loaded pipeline has changed significantly.

Specifically, the :ref:`element name <format_element_names>` used to declare
a junction no longer has any special significance, whereas in BuildStream 1
the junction's name is used to coalesce matching junctions in subprojects.

BuildStream 2 offers more flexibility in this regard, and allows you to *inherit*
a junction from a subproject, by using a :mod:`link <elements.link>` element directly
in place of a junction, and/or explicitly override the configuration of a subproject's
junction using the new ``overrides`` configuration attribute which the junction
element now provides.

Consult the :mod:`junction <elements.junction>` element documentation for a more
detailed explanation.


Migrated plugins
----------------
A majority of the plugins which used to be considered core plugins have been removed
from BuildStream in favor of a more modular and distributed approach. The remaining
core plugins are :ref:`documented here <plugins>`.

Any core plugins which you have been using in BuildStream 1 which have been migrated
to separate repositories will need to be accessed externally.

+---------------+-----------------------------------------------------------------------------------------+
| Plugin        | New location                                                                            |
+===============+=========================================================================================+
| **Element plugins**                                                                                     |
+---------------+-----------------------------------------------------------------------------------------+
| make          | `buildstream-plugins <https://pypi.org/project/buildstream-plugins/>`__                 |
+---------------+-----------------------------------------------------------------------------------------+
| autotools     | `buildstream-plugins <https://pypi.org/project/buildstream-plugins/>`__                 |
+---------------+-----------------------------------------------------------------------------------------+
| cmake         | `buildstream-plugins <https://pypi.org/project/buildstream-plugins/>`__                 |
+---------------+-----------------------------------------------------------------------------------------+
| distutils     | `buildstream-plugins <https://pypi.org/project/buildstream-plugins/>`__ (as setuptools) |
+---------------+-----------------------------------------------------------------------------------------+
| pip           | `buildstream-plugins <https://pypi.org/project/buildstream-plugins/>`__                 |
+---------------+-----------------------------------------------------------------------------------------+
| meson         | `buildstream-plugins <https://pypi.org/project/buildstream-plugins/>`__                 |
+---------------+-----------------------------------------------------------------------------------------+
| qmake         | `bst-plugins-experimental <https://pypi.org/project/bst-plugins-experimental/>`_        |
+---------------+-----------------------------------------------------------------------------------------+
| makemaker     | `bst-plugins-experimental <https://pypi.org/project/bst-plugins-experimental/>`_        |
+---------------+-----------------------------------------------------------------------------------------+
| modulebuild   | `bst-plugins-experimental <https://pypi.org/project/bst-plugins-experimental/>`_        |
+---------------+-----------------------------------------------------------------------------------------+
| **Source plugins**                                                                                      |
+---------------+-----------------------------------------------------------------------------------------+
| bzr           | `buildstream-plugins <https://pypi.org/project/buildstream-plugins/>`__                 |
+---------------+-----------------------------------------------------------------------------------------+
| git           | `buildstream-plugins <https://pypi.org/project/buildstream-plugins/>`__                 |
+---------------+-----------------------------------------------------------------------------------------+
| patch         | `buildstream-plugins <https://pypi.org/project/buildstream-plugins/>`__                 |
+---------------+-----------------------------------------------------------------------------------------+
| pip           | `buildstream-plugins <https://pypi.org/project/buildstream-plugins/>`__                 |
+---------------+-----------------------------------------------------------------------------------------+
| deb           | `bst-plugins-experimental <https://pypi.org/project/bst-plugins-experimental/>`_        |
+---------------+-----------------------------------------------------------------------------------------+
| ostree        | `bst-plugins-experimental <https://pypi.org/project/bst-plugins-experimental/>`_        |
+---------------+-----------------------------------------------------------------------------------------+
| zip           | `bst-plugins-experimental <https://pypi.org/project/bst-plugins-experimental/>`_        |
+---------------+-----------------------------------------------------------------------------------------+

.. attention::

   **YAML composition with externally loaded plugins**

   Note that when :ref:`YAML composition <format_composition>` occurs with plugins loaded
   from external projects, the *plugin defaults* will be composited with *your project.conf*
   and not with the project.conf originating in the external project containing the plugin.


Example of externally loaded plugin
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
It is recommended to transition directly :ref:`loading these plugins through junctions <project_plugins_junction>`,
which can be done as follows.


Create an alias for PyPI in your project.conf
'''''''''''''''''''''''''''''''''''''''''''''

.. code:: yaml

   aliases:
     pypi: https://files.pythonhosted.org/packages/


Create buildstream-plugins-junction.bst
'''''''''''''''''''''''''''''''''''''''
Create a junction which accesses the release tarball of the plugin repository.

.. code:: yaml

   kind: junction
   sources:
   - kind: tar
     url: pypi:e2/d8/ed9e849a1386297f854f9fa0200f3fa108498c0fdb5c86468c1601c7e571/buildstream-plugins-1.91.0.tar.gz
     ref: 44c6ea15d15476b68d0767c1d410d416f71544e57be572201058f8b3d3b05f83


Declare the plugin you want to use in your project.conf
'''''''''''''''''''''''''''''''''''''''''''''''''''''''
This will make the ``make`` and ``meson`` element plugins from the
`buildstream-plugins <https://github.com/apache/buildstream-plugins/>`__ project available for use in your project.

.. code:: yaml

   plugins:
   - origin: junction
     junction: buildstream-plugins-junction.bst
     elements:
     - make
     - meson


Miscellaneous
-------------
Here we list some miscellaneous breaking changes to the format in general.


Element naming
~~~~~~~~~~~~~~
The names of elements have :ref:`become more restrictive <format_element_names>`, for example
they must have the ``.bst`` extension.


Overlap whitelist
~~~~~~~~~~~~~~~~~
The :ref:`overlap whitelist <public_overlap_whitelist>`, which is the public data
found on elements which indicate which files an element can overwrite, must now
be expressed with absolute paths.


Strip commands
~~~~~~~~~~~~~~
The default ``strip-commands`` which :mod:`BuildElement <buildstream.buildelement>` implementations
use to split out debug symbols from binaries have been removed.

This can be solved by declaring a value for the ``%{strip-binaries}`` variable which
will be used for this purpose.
