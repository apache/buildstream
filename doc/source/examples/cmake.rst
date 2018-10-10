
.. _examples_cmake:

Using Cmake
===========

Intro
-----

This example aims to show:

 * How to use cmake elements


Prerequisites
-------------
All the necessary elements are in the example folder

Project structure
-----------------

This example has a common structure of a base.bst and a base/* folder contating
a link to something to provide the build elements. The project.comf contains
aliases to keep things easy to read and the build is controled with a single
hello.bst element.


``elements/hello.bst``
~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/cmake/elements/hello.bst
   :language: yaml

The only diffrence to any other non cmake projcet is the use of the 
:mod:`cmake <elements.cmake>` element to build our sample "Hello World" program.

We use a :mod:`local <sources.local>` source to obtain the sample
cmake project, but normally you would probably use a :mod:`git <sources.git>`
or other source to obtain source code from another repository.

Setting `kind` to `cmake` is enough to trigger the use of cmake and bst will
formate your build options like ``command-subdir`` and ``conf-root`` for cmake
but bst dose not provide the cmake program its self, you must specify that you
want cmake to be a dependency this is done by depending on the`base.bst` element
that provides cmake.


Expected usage
--------------

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

