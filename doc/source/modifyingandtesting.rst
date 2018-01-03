:orphan:

.. _modifyingandtesting:

Modifying and testing code
==========================

Creating a workspace
--------------------

A workspace is a directory containing a copy of a given project element's source code and is usually used when you want to modify and test your code, without changing the original.

Workspaces allow you to reduce the time taken to edit/compile/test your work by allowing you to build and test changes without needing to adjust the specific project elements directly or having to publish intermediate commits of your temporary work.

The following example assumes you have a project that can be built (Has the appropriate .bst files in place)

.. note::

  The project does not need to build sucessfully, only have the ability to build

.. If not, go to :ref:`buildproject`

In this example we be using `gedit.bst`, but this will work on any buildable project

----

To start off, we will be using the :ref:`invoking_workspace` command in order to create a copy of your project files in a declared directory

From the root of the project directory run:

.. code:: bash

 mkdir ~/WORKSPACES
 bst workspace open core/gedit.bst ~/WORKSPACES/gedit

This will create a new directory called "workspace1" in the current directory

.. code:: bash

 ls

 elements  files  keys  project.conf  workspace1

Modifying code in the workspace
-------------------------------

To modify the workspace copy of your project more easily, we will now move to the workspace directory

.. code:: bash

 cd workspace1

In here you will see the the contents of the source repository.

This is the same source that would normally be used to build the selected element.

.. code:: bash

 ls

 AUTHORS  autogen.sh  ChangeLog  configure.ac  CONTRIBUTING.md
 COPYING  data  docs  gedit  gedit.doap  git.mk  HACKING  help
 libgd  m4  MAINTAINERS  Makefile.am  NEWS  osx  plugins  po
 README  tools  win32


.. note::

 For sources which originate from a git repository, the workspace will be in 'detached HEAD' state and point to the exact revision which would normally be built. You can checkout the master branch and pull or push changes to the upstream directly from an open workspace.


Using the text editing tool of your choice, you can now open these files and make any modifications that you wish to the elements source code.


Rebuilding the project using open workspaces
--------------------------------------------

Return to the root of your original project and then rebuild the project as normal using:

.. code:: bash

 bst build core/gedit.bst

Instead of building gedit from the originally defined sources, BuildStream will use the sources directly from the open workspace.
This will happen for all elements that have a workspace attached to them.

Verifying changes
-----------------

You can use the :ref:`invoking_shell` command to launch a sandboxed shell environment where the built gedit artifact and it's runtime dependencies are staged. 

.. code:: bash

 bst shell core/gedit

You can now launch the gedit application you have built and inspect the behavior. You can also debug it with any tools found in the sandboxed runtime environment, such as gdb or valgrind.

Closing a workspace
-------------------

Once you are finished with the workspace, you can use the :ref:`invoking_workspace_close` command to detach the workspace from the element.

This is done by returning to the project directory and running:

.. code:: bash

 bst workspace close core/gedit.bst

This will remove the references to the workspace from the element and allow it to use the original sources.

.. note::

 The directory and its contents will not be removed.

 The `--remove-dir` flag can be used alongside the previous command in order to remove the closed workspace.
