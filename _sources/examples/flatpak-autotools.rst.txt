
.. _examples_flatpak_autotools:

Building on a Flatpak SDK
=========================
Here we demonstrate how to build and run software using
a Flatpak SDK for the base runtime.

.. note::

   This example is distributed with BuildStream
   in the `doc/examples/flatpak-autotools
   <https://github.com/apache/buildstream/tree/master/doc/examples/flatpak-autotools>`_
   subdirectory.


Project structure
-----------------

The following is a simple :ref:`project <projectconf>` definition:

``project.conf``
~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/flatpak-autotools/project.conf
   :language: yaml

Here we use an :ref:`arch option <project_options_arch>` to allow
conditional statements in this project to be made depending on machine
architecture. For this example we only support the ``i386`` and ``x86_64``
architectures.

Note that we've added a :ref:`source alias <project_source_aliases>` for
the ``https://dl.flathuhb.org/`` repository to download the SDK from.


``elements/base/sdk.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/flatpak-autotools/elements/base/sdk.bst
   :language: yaml

This is the :mod:`import <elements.import>` element used to import the
actual Flatpak SDK, it uses an :mod:`ostree <sources.ostree>` source to
download the Flatpak since these are hosted in OSTree repositories.

While declaring the :mod:`ostree <sources.ostree>` source, we specify a GPG
public key to verify the OSTree download. This configuration is optional
but recommended for OSTree repositories. The key is stored in the project directory
at ``keys/gnome-sdk.gpg``, and can be downloaded from https://sdk.gnome.org/keys/.

We also use :ref:`conditional statements <format_directives_conditional>` to decide
which branch to download.

For the ``config`` section of this :mod:`import <elements.import>` element,
it's important to note two things:

* **source**: We only want to extract the ``files/`` directory from the SDK,

  This is becase Flatpak runtimes dont start at the root of the OSTree checkout,
  instead the actual files start in the ``files/`` subdirectory

* **target**: The content we've extracted should be staged at ``/usr``

  This is because Flatpak runtimes only contain the data starting at ``/usr``,
  and they expect to be staged at ``/usr`` at runtime, in an environment
  with the appropriate symlinks setup from ``/``.


``elements/base/usrmerge.bst``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/flatpak-autotools/elements/base/usrmerge.bst
   :language: yaml

This is another :mod:`import <elements.import>` element, and it uses
the :mod:`local <sources.local>` source type so that we can stage files
literally stored in the same repository as the project.

The purpose of this element is simply to add the symlinks for
``/lib -> /usr/lib``, ``/bin -> /usr/bin`` and ``/etc -> /usr/etc``, we
have it depend on the ``base/sdk.bst`` element only to ensure that
it is staged *after*, i.e. the symlinks are created after the SDK is staged.

As suggested by the ``.bst`` file, the symlinks themselves are a part
of the project and they are stored in the ``files/links`` directory.


``elements/base.bst``
~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/flatpak-autotools/elements/base.bst
   :language: yaml

This is just a :mod:`stack <elements.stack>` element for convenience sake.

Often times you will have a more complex base to build things on, and it
is convenient to just use a :mod:`stack <elements.stack>` element for
your elements to depend on without needing to know about the inner workings
of the base system build.


``elements/hello.bst``
~~~~~~~~~~~~~~~~~~~~~~

.. literalinclude:: ../../examples/flatpak-autotools/elements/hello.bst
   :language: yaml

Finally, we show an example of an :mod:`autotools <elements.autotools>` element
to build our sample "Hello World" program.

We use another :mod:`local <sources.local>` source to obtain the sample
autotools project, but normally you would probably use a :mod:`git <sources.git>`
or other source to obtain source code from another repository.


Using the project
-----------------
Now that we've explained the basic layout of the project, here are
just a few things you can try to do with the project.

.. note::

   The following examples assume that you have first changed your working
   directory to the
   `project root <https://github.com/apache/buildstream/tree/master/doc/examples/flatpak-autotools>`_.


Build the hello.bst element
~~~~~~~~~~~~~~~~~~~~~~~~~~~
To build the project, run :ref:`bst build <invoking_build>` in the
following way:

.. raw:: html
   :file: ../sessions/flatpak-autotools-build.html


Run the hello world program
~~~~~~~~~~~~~~~~~~~~~~~~~~~
The hello world program has been built into the standard ``/usr`` prefix,
and will automatically be in the default ``PATH`` for running things
in a :ref:`bst shell <invoking_shell>`.

To just run the program, run :ref:`bst shell <invoking_shell>` in the
following way:

.. raw:: html
   :file: ../sessions/flatpak-autotools-shell.html
