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

then install wget or some other download tool

----

If not already installed, install `git`

This example will be using `gnome-modulesets`, but this will apply to any buildable repo

git clone: http://gnome7.codethink.co.uk/gnome-modulesets.git/
 
Then move into the repo

Building
----

Find the .bst file that you want to build

In this case, we will be using `gedit.bst` in elements/core 

from the root of the project repo run:

    ``bst`` :ref:`invoking_build` ``[project bst file]``

In this case, that would be core/gedit.bst

This will try to build the project.

----

If you get an error requesting the use of ``bst track``

run:
    ``bst`` :ref:`invoking_track` ``--deps all [project bst file]``

This command updates all project dependencies.

Run the build command again and this time it should succeed.

