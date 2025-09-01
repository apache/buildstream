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



.. _developing_workspaces:

Workspaces
==========
In this section we will cover the use of BuildStream's workspaces feature when
devloping a BuildStream project.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/developing
   <https://github.com/apache/buildstream/tree/master/doc/examples/developing>`_
   subdirectory.

We will start with the project used in the :ref:`running commands <tutorial_running_commands>`
tutorial. Recall the element hello.bst, which builds the bellow C file:

.. literalinclude:: ../../examples/developing/files/src/hello.c
   :language: c

Suppose we now want to alter the functionality of the *hello* command. We can
make changes to the source code of Buildstream elements by making use of
BuildStream's workspace command.


Opening a workspace
-------------------
First we need to open a workspace, we can do this by running

.. raw:: html
   :file: ../sessions/developing-workspace-open.html

This command has created the workspace_hello directory in which you can see
the source for the hello.bst element, i.e. hello.c and the corresponding
makefile.

You can view existing workspaces using

.. raw:: html
   :file: ../sessions/developing-workspace-list.html


Making code changes
-------------------
Let's say we want to alter the message printed when the hello command is run.
We can open workspace_hello/hello.c and make the following change:

.. literalinclude:: ../../examples/developing/update.patch
    :language: diff

Now, rebuild the hello.bst element.

.. raw:: html
   :file: ../sessions/developing-build-after-changes.html

Note that if you run the command from inside the workspace, the element name is optional.

.. raw:: html
   :file: ../sessions/developing-build-after-changes-workspace.html

Now running the hello command using bst shell:

.. raw:: html
   :file: ../sessions/developing-shell-after-changes.html

This gives us the new message we changed in hello.c.

From this point we have several options. If the source is under version control
we can commit our changes and push them to the remote repository.


Incremental builds
------------------
Once you have opened up your workspace, the workspace build directory will be
reused for subsequent builds, which should improve your edit/compile/test cycle
time when working with an open workspace.

In order to optimize incremental builds, BuildStream treats build configure steps
separately from the main build steps, and will only call the
:func:`Element.prepare() <buildstream.element.Element.prepare>` method on
an element plugin the first time it gets built. This avoids needlessly rebuilding
objects due to header files and such being unconditionally recreated by configuration
scripts (such as the typical ``./configure`` script which is called for ``autotools``
elements for instance).

A caveat of this optimization however is that changes you might make to the
configuration scripts will not be taken into account by default on the next
incremental build. A forced reconfiguration can also be required in some cases
where build scripts automatically detect sources in it's configuration phase,
so newly added sources you add might be ignored.

In order to force the configuration step to be called again on the next build,
you can use :ref:`bst workspace reset --soft <invoking_workspace_reset>`, like so:

In these cases, you can perform a hard reset on the workspace using
:ref:`bst workspace reset <invoking_workspace_reset>`, like so:

.. raw:: html
   :file: ../sessions/developing-soft-reset.html

This will ensure that the next time you run the build, BuildStream will forcefully
rerun the :func:`Element.prepare() <buildstream.element.Element.prepare>` method
and cause the configuration step to occur again.


Closing your workspace
----------------------
If we want to close the workspace and come back to our changes later, we can

.. raw:: html
   :file: ../sessions/developing-close-workspace.html

We can then reopen the workspace later using:

.. raw:: html
   :file: ../sessions/developing-reopen-workspace.html

The --no-checkout option tells BuildStream not to check the source out but to
instead hard-link to the workspace_hello directory.

Alternatively, if we wish to discard the changes we can use

.. raw:: html
   :file: ../sessions/developing-reset-workspace.html

This resets the workspace to its original state.

To discard the workspace completely we can do:

.. raw:: html
   :file: ../sessions/developing-discard-workspace.html

This will close the workspace and completely remove the workspace_hello
directory.

