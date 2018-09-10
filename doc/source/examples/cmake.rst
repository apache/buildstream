
.. _examples_cmake:

Using Cmake
===========

Intro
-----

This example aims to show:

 * How to use cmake elements
 * How to use Out of source element with cmake

The out of source hello world example show the basics of out of source builds but
this example shows how to apply that to cmake, a more complex build system.

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

.. literalinclude:: ../../examples/cmake/project.conf
   :language: yaml

Note that we’ve added a :ref:`source alias <project_source_aliases>` for
the ``https://gnome7.codethink.co.uk/tarballs/`` repository to download the 
build tools from, please note that this bootstrap only contains the compiler 
if you wish to use c++ you will need a different bootstrap.

``elements/base/alpine.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/cmake/elements/base/alpine.bst
   :language: yaml

This is the :mod:`import <elements.import>` element used to import the
actual Flatpak SDK, it uses an :mod:`tar <sources.tar>` source to
download and unpack the archive in to the sandbox.

``elements/base.bst``
~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/cmake/elements/base.bst
   :language: yaml

This is just a :mod:`stack <elements.stack>` element for convenience sake.

Often times you will have a more complex base to build things on, and it
is convenient to just use a :mod:`stack <elements.stack>` element for
your elements to depend on without needing to know about the inner workings
of the base system build.

``elements/hello.bst``
~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/cmake/elements/hello.bst
   :language: yaml

Finally, we show an example of an :mod:`cmake <elements.cmake>` element
to build our sample "Hello World" program.

We use a :mod:`local <sources.local>` source to obtain the sample
cmake project, but normally you would probably use a :mod:`git <sources.git>`
or other source to obtain source code from another repository.

Setting `kind` to `cmake` is enough to trigger the use of cmake and bst will
formate your build options like ``command-subdir`` and ``conf-root`` for cmake
but bst dose not provide the cmake program its self, you must specify that you
want cmake to be a dependency this is done by depending on the`base.bst` element
that provides cmake.


Using the project
-----------------
Now that we've explained the basic layout of the project, here are
just a few things you can try to do with the project.

.. note::

   The following examples assume that you have first changed your working
   directory to the
   `project root <https://gitlab.com/BuildStream/buildstream/tree/master/doc/examples/cmake>`_.


Build the hello.bst element
~~~~~~~~~~~~~~~~~~~~~~~~~~~
To build the project, run :ref:`bst build <invoking_build>` in the
following way:

.. raw:: html
   :file: ../sessions/cmake-build.html


Run the hello world program
~~~~~~~~~~~~~~~~~~~~~~~~~~~
The hello world program has been built into the standard ``/usr`` prefix,
and will automatically be in the default ``PATH`` for running things
in a :ref:`bst shell <invoking_shell>`.

To just run the program, run :ref:`bst shell <invoking_shell>` in the
following way:

.. raw:: html
   :file: ../sessions/cmake-shell.html











