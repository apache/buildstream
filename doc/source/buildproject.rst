.. _buildproject:

Building a basic project
====

This Section assumes you have installed Buildstream already.

If not, go to :ref:`installing`

Or :ref:`docker`


Setup
----

If using docker, run::

  bst-here 

in the directory you want to use

----

If not already installed, install `git`

This example will be using `gnome-modulesets`, but this will apply to any buildable repo

Download :download:`gnome modulesets <example_projects/gnome-modulesets.tar>`
 
Then move into the repo

Building
----

Find the .bst file that you want to build

In this case, we will be using `gedit.bst` in elements/core 

from the root of the project repo run:

    ``bst`` :ref:`invoking_build` ``gedit.bst``

In this case, that would be core/gedit.bst

This will try to build the project.

----

If you get an error requesting the use of ``bst track``

run:
    ``bst`` :ref:`invoking_track` ``--deps all gedit.bst``

This command updates all project dependencies.

Run the build command again and this time it should succeed.

