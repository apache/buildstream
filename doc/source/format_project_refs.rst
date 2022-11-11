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



.. _projectrefs:

The project.refs file
=====================
If one has elected to store source references in a single ``project.refs``
file, then it will be stored at the toplevel of your project directory
adjacent to ``project.conf``. This can be configured in your project
using the :ref:`ref-storage configuration <project_format_ref_storage>`

Sources for :mod:`junction <elements.junction>` elements are stored
separately in an adjacent ``junction.refs`` file of the same format.


.. _projectrefs_basics:

Basic behavior
--------------
When a ``project.refs`` file is in use, any source references found
in the :ref:`inline source declarations <format_sources>` are considered
invalid and will be ignored, and a warning will be emitted for them.

When ``bst source track`` is run for your project, the ``project.refs`` file
will be updated instead of the inline source declarations. In the absence
of a ``project.refs`` file, ``bst source track`` will create one automatically
with the tracking results.

An interesting property of ``project.refs`` is that it allows for
*cross junction tracking*. This is to say that it is possible to override
the *ref* of a given source in a project that your project depends on via
a :mod:`junction <elements.junction>`, without actually modifying the
junctioned project.


.. _projectrefs_format:

Format
------
The ``project.refs`` uses the same YAML format used throughout BuildStream,
and supports the same :ref:`directives <format_directives>` which apply to
``project.conf`` and element declaration files (i.e. *element.bst* files).

The ``project.refs`` file format itself is very simple, it contains a single ``projects``
key at the toplevel, which is a dictionary of :ref:`project names <project_format_name>`.
Each *project name* is a dictionary of *element names*, and each *element name* holds
a list of dictionaries corresponding to the element's :ref:`sources <format_sources>`.


**Example**

.. code:: yaml

   # Main toplevel "projects" key
   projects:

     # The local project's name is "core"
     core:

       # A dictionary of element names
       base/automake.bst:

       # A list of sources corresponding to the element
       # in the same order in which they were declared.
       #
       # The values of this list are dictionaries of the
       # symbolic "ref" portion understood by the given
       # source plugin implementation.
       #
       - ref: af6ba39142220687c500f79b4aa2f181d9b24e4...

     # The "core" project depends on the "bootstrap" project,
     # here we are allowed to override the refs for the projects
     # we depend on through junctions.
     bootstrap:

       zlib.bst:
       - ref: 4ff941449631ace0d4d203e3483be9dbc9da4540...
