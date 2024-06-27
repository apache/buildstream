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


.. _plugins:

Plugin specific documentation
=============================
Plugins provide their own individual plugin specific YAML configurations,
The element ``.bst`` files can specify plugin specific configuration in
the :ref:`config section <format_config>`, while sources declared on a
given element specify their plugin specific configuration directly
:ref:`in their source declarations <format_sources>`.


.. _plugins_elements:

Elements
--------
.. toctree::
   :maxdepth: 1

   elements/stack
   elements/import
   elements/compose
   elements/script
   elements/link
   elements/junction
   elements/filter
   elements/manual


.. _plugins_sources:

Sources
-------

All source plugins can be staged into an arbitrary directory within the build
sandbox with the ``directory`` option.
See :ref:`Source class built-in functionality <core_source_builtins>` for more
information.

.. toctree::
   :maxdepth: 1

   sources/local
   sources/remote
   sources/tar


.. _plugins_external:

External plugins
----------------
External plugins need to be :ref:`loading through junctions <project_plugins_junction>`,
or alternatively installed separately in the python environment where you are
running BuildStream and loaded using the :ref:`pip method <project_plugins_pip>`.

Here is a list of BuildStream plugin projects known to us at this time:

* `buildstream-plugins <https://github.com/apache/buildstream-plugins/>`_
* `bst-plugins-experimental <http://buildstream.gitlab.io/bst-plugins-experimental/>`_
* `bst-plugins-container <https://pypi.org/project/bst-plugins-container/>`_
