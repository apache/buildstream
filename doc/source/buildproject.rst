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

This example will be using `gnome-modulesets`, but this will apply to any buildable repo

Download or clone `gnome-Modulesets  <http://gnome7.codethink.co.uk/gnome-modulesets.git/>`_

Then move into the repo

Building
----

Find the .bst file that you want to build

In this case, we will be using `gedit.bst` in elements/core 

from the root of the project repo run:

    ``bst`` :ref:`invoking_build` ``core/gedit.bst``

This will try to build the project.

In this case, Gedit uses "autotools", so will therefore run:

* `autoreconf;`
* `./configure;`
* `make;` 
* `make install`

Buildstream will run the commands needed to build each plugin in the same way the user would.

This removes the need for the user to type dozens of different commands if using multiple build files

----

If you get an error requesting the use of ``bst track``

This occurs when a ref has not been provided for an elements source. 

This means that buildstream does not know where to look to download something.

``bst`` :ref:`invoking_track` resolves this issue by checking for the latest commit on the branch provided in the source of the file.

There are 2 main ways of resolving this:

1: run ``bst`` :ref:`invoking_track` `` [element]

Where element is the element listed in the error message

2: run: ``bst`` :ref:`invoking_track` ``--deps all core/gedit.bst``

This command will go through each element and repeat the process of tracking them.

After tracking all untracked elements

Run the build command again and this time it should succeed.

