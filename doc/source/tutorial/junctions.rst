.. _tutorial_junctions:

Depending on other BuildStream projects
=======================================
In :ref:`the last chapter <tutorial_running_commands>` we saw how
BuildStream can be used to compile a simple C project. We used a
slightly modified Alpine tarball for this.

While this works, and is not an uncommon practice, this way we lose
out on some of BuildStream's features, and cannot necessarily
reproduce the whole system from scratch. We would also need to supply
different base images for different architectures if we wanted to
support more than ``x86_64``. It would be better if we could use
BuildStream elements to build everything from scratch, but this would
take a lot of effort.

Instead, in this chapter, we will introduce the concept of "junctions"
that allow us to depend on other BuildStream projects, so that we can
have a definition of the whole system without needing to specify every
detail ourselves.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/junctions
   <https://gitlab.com/BuildStream/buildstream/tree/master/doc/examples/autotools>`_
   subdirectory.


Overview
--------
In this example we will replace the ``elements/base.bst`` and
``elements/base/alpine.bst`` elements with a junction to
`freedesktop-sdk <https://freedesktop-sdk.io/>`_.


Project structure
-----------------

For this project, we will only use two element declarations, and the
usual ``project.conf``, with some slight modifications.

If we look at what this project builds using :ref:`bst show
<invoking_show>` we will see a pipeline with a lot more elements than
we defined:

..
   .. raw:: html
      :file: ../sessions/junctions-show-before.html

.. note::

   You will likely need to fetch the freedesktop-sdk project first. To
   do so, simply run ``bst source fetch freedesktop-sdk.bst`` as
   suggested.

This is because we use a number of elements from the freedesktop-sdk
junction. Those are clearly marked with a ``freedesktop-sdk:``
prefix. In fact, the only element we seem to define is ``hello.bst``.

Let's explain the files that we do define:

.. _tutorial_junctions_project_conf:


``project.conf``
~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/junctions/project.conf
   :language: yaml

freedesktop-sdk provides bindings for multiple architectures, but to
use these we need to add an :ref:`option <project_options>` to
``project.conf``. We define options for ``arm``, ``aarch64``, ``i686``
and ``x86_64``. BuildStream will automatically pick the correct
architecture for our system.


``elements/freedesktop-sdk.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/junctions/elements/freedesktop-sdk.bst
   :language: yaml

This is the magic element that allows us to access elements from
another project. We instruct BuildStream to clone the freedesktop-sdk
project and use its ``18.08`` branch, which is the recommended version
at the time of writing this guide.

We also set the ``target_arch`` option to the option we defined in
``project.conf`` - if we only wanted to target one architecture, we
could specify a specific architecture here.


``elements/hello.bst``
~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/junctions/elements/hello.bst
   :language: yaml

Finally, we modify our build element. We replace our Alpine-based base
system with an element from freedesktop sdk -
`public-stacks/buildsystems.bst
<https://gitlab.com/freedesktop-sdk/freedesktop-sdk/blob/master/elements/public-stacks/buildsystems.bst>`_. We
do this using a normal dependency, but we specify the junction from
which to take the element by prepending the element name with
``freedesktop-sdk.bst``, which refers to our junction element.

Since the ``freedesktop-sdk.bst:public-stacks/buildsystems.bst``
element provides all runtime components we need for our build, just
like alpine did, we need to make no other changes.

Using the project
-----------------

This project can be used in exactly the same way the
:ref:`running_commands <tutorial_running_commands>` project was used -
we build and run ``hello.bst``. The difference is that ``bst show``
will now list every individual component, as we saw earlier.

Build the hello.bst element
~~~~~~~~~~~~~~~~~~~~~~~~~~~

To build the project, run :ref:`bst build <invoking_build>` in the
following way:

..
   .. raw:: html
      :file: ../sessions/junctions-build.html

BuildStream will automatically build elements provided by the
freedesktop-sdk project, and even download ready-made binaries
wherever possible. It then uses ``make`` and the C compiler provided
by freedesktop-sdk to build our hello world program.

All the elements, including the freedesktop-sdk elements, will now
show up as ``cached`` in the pipeline:

..
   .. raw:: html
      :file: ../sessions/junctions-show-after.html

Run the hello world program
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Just like in the previous example, we can run our program using
:ref:`bst shell <invoking_shell>`:

..
   .. raw:: html
      :file: ../sessions/junctions-shell.html

Summary
-------

In this chapter we introduced the concept of project junctions, and
explained how they can be used to define a basic sysroot that is
transparent to buildstream.
