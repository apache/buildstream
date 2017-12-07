.. _modifyingandtesting:

Modifying and testing code
====

Creating a workspace
----

A work space is a seperate directory containing a copy of the project sourcecode

In this example, we will again be using gedit.bst, but this will work on any buildable project

----

From the root of the project directory run:

    ``bst workspace open core/gedit.bst ../workspace1``

You now have an external copy of your project to work with.


Modifying code in the workspace
----

To modify the workspace copy of your project, you will have to move to the workspace directory

    ``cd ../workspace1``

Here you will see the output of your build.

Move to the sourcecode directory, in this case, gedit

    ``cd gedit/``

Using the text editing tool of your choice, you can now open these files and make any modifications that you wish.


Rebuilding the workspace project
----

Return to the root of your original project

And then rebuild the project as normal.

Buildstream will redirect itself to the workspace that you opened before

and build that instead of the original.


Verifying changes
----

You can now use the shell command from the project root to run your project again.

E.G:

    ``bst shell core/gedit``

You should now see any changes that you made.

