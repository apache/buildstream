
.. _examples_out_of_source_build_helloworld:


Out of source hello world
=========================

Intro
-----

This example aims to show:

 * How to use Out of source element with cmake

This example aims to show the basics of out of source builds

Build stream aims to make out of source builds as easy as posible and so long as
the build element supports out of source element it should be the same.

The out of source builds are configured by setting:
 
 * `directory` of the source, this sets the source to open in to a folder in the
   build root.
 * `command-subdir` variable, sets were the build will be run.
 * `conf-root` variable, tells the confirmation tool how to get from
   `command-subdir` to `directory`.

This example:
 
 * Sets `directory` to `Source` in `elements/hello.bst`
 * Sets `command-subdir` to `build` in `elements/hello.bst`
 * Sets `conf-root` to `"%{build-root}/Source"` in `elements/hello.bst`

This way we can change `command-subdir` with out having to change `conf-root`
but we could have set `conf-root` to `../Source` but then we would have to
change it if `command-subdir` changed to `.` or `sub/folder`



Prerequisites
-------------
All the necessary elements are in the example folder

Project structure
-----------------

The following is a simple :ref:`project <projectconf>` definition:

``project.conf``
~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/out-of-source-build-helloworld/project.conf
   :language: yaml

Note that we’ve added a :ref:`source alias <project_source_aliases>` for
the ``https://gnome7.codethink.co.uk/tarballs/`` repository to download the 
build tools from.

``elements/base/alpine.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/out-of-source-build-helloworld/elements/base/alpine.bst
   :language: yaml

This is the :mod:`import <elements.import>` element used to import the
actual Flatpak SDK, it uses an :mod:`tar <sources.tar>` source to
download and unpack the archive in to the sandbox.

``elements/base.bst``
~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/out-of-source-build-helloworld/elements/base.bst
   :language: yaml

This is just a :mod:`stack <elements.stack>` element for convenience sake.

Often times you will have a more complex base to build things on, and it
is convenient to just use a :mod:`stack <elements.stack>` element for
your elements to depend on without needing to know about the inner workings
of the base system build.

``elements/hello.bst``
~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/out-of-source-build-helloworld/elements/hello.bst
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
   `project root <https://gitlab.com/BuildStream/buildstream/tree/master/doc/examples/out-of-source-build-helloworld>`_.

Build the hello.bst element
~~~~~~~~~~~~~~~~~~~~~~~~~~~
To build the project, run :ref:`bst build <invoking_build>` in the
following way:

.. raw:: html
   :file: ../sessions/outofsource-helloworld-build.html

Please see the source option `directory` and variables, `command-subdir` and 
`conf-root` set as described in the introduction.

Run the hello world program
~~~~~~~~~~~~~~~~~~~~~~~~~~~
The hello world program has been built into the standard ``/usr`` prefix,
and will automatically be in the default ``PATH`` for running things
in a :ref:`bst shell <invoking_shell>`.

To just run the program, run :ref:`bst shell <invoking_shell>` in the
following way:

.. raw:: html
   :file: ../sessions/outofsource-helloworld-shell.html












