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



.. _junction_workspaces:

Workspaces and subprojects
==========================
When developping a project with :mod:`junctions <elements.junction>` and
subprojects, you will probably end up needing to work on the subprojects
as well.

Opening :ref:`workspaces <developing_workspaces>` works mostly in the
same way as it does with subprojects as it does for elements directly
in your own project.

.. note::

    This section runs commands on the same example project presented in the
    :ref:`previous section <junction_elements>`, which is distributed with BuildStream in the
    `doc/examples/junctions <https://github.com/apache/buildstream/tree/master/doc/examples/junctions>`_
    subdirectory.


Workspacing a junction
----------------------
Sometimes you need to work on the elements declared in a subproject
directly. As the downstream consumer of a junctioned project, it makes
sense that you might need to work on that project as well in order
to satisfy the needs of your downstream project.

You can easily work on your subproject by :ref:`opening a workspace <invoking_workspace_open>`
on the junction element directly.

.. raw:: html
   :file: ../sessions/junctions-workspace-open-subproject.html

After opening a workspace on the junction element, the open workspace
is used to define the subproject, allowing you to make changes to
how the subproject is built, add new dependencies and configure the
subproject in any way.


Cross-junction workspaces
-------------------------
You can open workspaces for elements in the project refered to by the junction
using the syntax ``bst open ${junction-name}:{element-name}``. In this example,

.. raw:: html
   :file: ../sessions/junctions-workspace-open.html

This has opened a workspace for the hello.bst element from the autotools project.
This workspace can now be used as normal.
