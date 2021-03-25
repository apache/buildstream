

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

Making bigger changes
---------------------

The first time you build with your workspace BuildStream behaves very similarly to
normal. However for subsequent builds it does not run the configuration commands and
only runs the build commands. This can result in significant speed ups as the configuration
commands can be slow (maybe 20+ minutes for a moderate sized element)

Sometimes you do need to rerun the configuration command for a open workspace, this
can be done by resetting the workspace, and then running a build. However this will
cause all of your incremental work to be lost. In this case running a soft reset will
reset the trigger to run the configuration commands but will not change any files in you
workspace.

Reasons to soft reset a workspace include:
  * changing the configuration command of a element.
  * adding a new source that the configure command will spot and enable more code.

The soft reset can be performed by:

.. raw:: html
   :file: ../sessions/developing-soft-reset.html

Then the next build will include the configuration commands. You must reset the workspace
every time you wish to trigger the configuration commands as only the first build
after the reset will run them.

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

