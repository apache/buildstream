.. _modifyingandtesting:

Modifying and testing code
====

Creating a workspace
----

A work space is a seperate directory containing a copy of the project sourcecode.
This would usually be used when you want to modify and test your code, without changing the original.
This is very useful for trying out new patches and changes without risking loss of work.

This example assumes you have a project that can be built (Has the appropriate .bst files in place)
`Note: The project does not need to build sucessfully, only have the ability to build` 

If not, go to :ref:`buildproject`

In this example we be using `gedit.bst`, but this will work on any buildable project

----

From the root of the project directory run:

    ``bst`` :ref:`invoking_workspace` ``open gedit.bst workspace1``

In this case, that would be core/gedit.bst

This will create a copy of your project files in the declared directory

And give you an external copy of your project to work with.


Modifying code in the workspace
----

To modify the workspace copy of your project, you will have to move to the workspace directory

    ``cd workspace1``

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

    ``bst`` :ref:`invoking_shell` ``core/gedit``

You should now see any changes that you made.

