

.. _developing_workspaces:

Workspaces
==========
In this section we will cover the use of BuildStream's workspaces feature when devloping on a 
BuildStream project.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/developing
   <https://gitlab.com/BuildStream/buildstream/tree/master/doc/examples/developing>`_
   subdirectory.

We will start with the project used in the :ref:`running commands <tutorial_running_commands>`
tutorial. Recall the element hello.bst, which builds the bellow C file:

.. literalinclude:: ../../examples/developing/files/src/hello.c
   :language: c

Suppose we now want to alter the functionality of the *hello* command. We can
make changes to the source code of Buildstream elements by making use of
BuildStream's workspace command.

Utilising cached buildtrees
---------------------------
 When a BuildStream build element artifact is created and cached, a snapshot of
 the build directory after the build commands have completed is included in the
 artifact. This `build tree` can be considered an intermediary state of element,
 where the source is present along with any output created during the build
 execution.

 By default when opening a workspace, bst will attempt to stage the build tree
 into the workspace if it's available in the local cache. If the respective
 build tree is not present in the cache (element not cached, partially cached or
 is a non build element) then the source will be staged as is. The default
 behaviour to attempt to use the build tree can be overriden with specific bst
 workspace open option of `--no-cache`, or via setting user configuration option
 `workspacebuildtrees: False`


Opening a workspace
-------------------
.. note::

    This example presumes you built the hello.bst during
    :ref:`running commands <tutorial_running_commands>`
    if not, please start by building it.


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

.. note::

    bst reset will attempt to open the workspace in
    the condition in which it was originally staged,
    i.e with or without consuming the element build tree.
    If it was originally staged with a cached build tree
    and there's no longer one available, the source will
    be staged as is.

To discard the workspace completely we can do:

.. raw:: html
   :file: ../sessions/developing-discard-workspace.html

This will close the workspace and completely remove the workspace_hello
directory.

