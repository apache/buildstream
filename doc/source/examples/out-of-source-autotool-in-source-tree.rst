
.. _examples_out_of_source_autotool_in_source_tree:


Building a autotools project Out of source
==========================================

Intro
-----

This example aims to show:

 * How to use Out of source element with autotools were the project to be build
   is not in the sources root directory.

The out of source hello world example show the basics of out of source builds but
this example shows how to apply that to in source tree projects.

Build stream aims to make out of source builds as easy as possible and so long as
the build element supports out of source element it should be the same, so while
this is a auto tools project the principles of in source tree projects should
transfer to any buildsystem with support for out of source builds.


The out of source builds are configured by setting:

 * `directory` of the source, this sets the source to open in to a folder in the
   build root.
 * `command-subdir` variable, sets were the build will be run.
 * `conf-root` variable, tells the confirmation tool how to get from
   `command-subdir` to `directory`.

This example:

 * Sets `directory` to `SourB` in `elements/hello.bst`
 * Sets `command-subdir` to `build` in `elements/hello.bst`
 * Sets `conf-root` to `"%{build-root}/SourB/doc/amhello"` in `elements/hello.bst`

Commenly we have `conf-root` be the location of the source. Ether in absolute
terms, eg `%{build-root}/SourB` or in relative terms `../SourB`. But in our case
the projcet is not in the root of the source, it is in `doc/amhello` within the
source so we have to set `conf-root` to equal the location of the source plus
the location of the project within the source. eg. `"%{build-root}/SourB/doc/amhello"`

Prerequisites
-------------
All the necessary elements are in the example folder

Project structure
-----------------

The following is a simple :ref:`project <projectconf>` definition:

``project.conf``
~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/out-of-source-autotool-in-source-tree/project.conf
   :language: yaml

Note that we’ve added a :ref:`source alias <project_source_aliases>` for
the ``https://gnome7.codethink.co.uk/tarballs/`` repository to download the 
build tools from.

``elements/base/alpine.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/out-of-source-autotool-in-source-tree/elements/base/alpine.bst
   :language: yaml

This is the :mod:`import <elements.import>` element used to import the
actual Flatpak SDK, it uses an :mod:`tar <sources.tar>` source to
download and unpack the archive in to the sandbox.

``elements/base.bst``
~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/out-of-source-autotool-in-source-tree/elements/base.bst
   :language: yaml

This is just a :mod:`stack <elements.stack>` element for convenience sake.

Often times you will have a more complex base to build things on, and it
is convenient to just use a :mod:`stack <elements.stack>` element for
your elements to depend on without needing to know about the inner workings
of the base system build.

``elements/hello.bst``
~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/out-of-source-autotool-in-source-tree/elements/hello.bst
   :language: yaml

Finally, we show an example of an :mod:`automake <elements.autotools>` element
to build our sample "Hello World" program.

We use a :mod:`local <sources.local>` source to obtain the sample
autotools project, but normally you would probably use a :mod:`git <sources.git>`
or other source to obtain source code from another repository.


Using the project
-----------------
Now that we've explained the basic layout of the project, here are
just a few things you can try to do with the project.

.. note::

   The following examples assume that you have first changed your working
   directory to the
   `project root <https://gitlab.com/BuildStream/buildstream/tree/master/doc/examples/out-of-source-autotool-in-source-tree>`_.

Build the hello.bst element
~~~~~~~~~~~~~~~~~~~~~~~~~~~
To build the project, run :ref:`bst build <invoking_build>` in the
following way:

.. raw:: html
   :file: ../sessions/outofsource-autotools-build.html


Run the hello world program
~~~~~~~~~~~~~~~~~~~~~~~~~~~
The hello world program has been built into the standard ``/usr`` prefix,
and will automatically be in the default ``PATH`` for running things
in a :ref:`bst shell <invoking_shell>`.

To just run the program, run :ref:`bst shell <invoking_shell>` in the
following way:

.. raw:: html
   :file: ../sessions/outofsource-autotools-shell.html










