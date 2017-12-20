.. _postbuild:

What you can do with a built project
====

Once you have successfully built a project with Buildstream, 
there are 3 things you can do with it:

- :ref:`invoking_shell` 
- :ref:`invoking_checkout`
- :ref:`invoking_workspace`

Shell
----

This command allows you to peek inside of a built project. 
This is useful for debugging and ensuring the system built everything properly

Checkout
----

This command returns all :ref:`artifacts <artifacts>` that are defined in the install-root

Workspace
----

This command returns the source code of the target project to a target directory,
providing you with a safe copy of your sourcecode to modify.

