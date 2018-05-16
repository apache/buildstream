
.. _examples_flatpak_autotools:

Using flatpak runtimes to build and run from source
===================================================
Here we demonstrate how to build and run software using
a Flatpak SDK for the base runtime.

Config files

- project.conf

.. literalinclude:: ../examples/flatpak-autotools/project.conf
   :language: yaml

- element

.. literalinclude:: ../examples/flatpak-autotools/elements/flatpak-autotools.bst
   :language: yaml

- element

.. literalinclude:: ../examples/flatpak-autotools/elements/dependencies/usrmerge.bst
   :language: yaml

Building::

   bst build flatpak-autotools.bst

Running::

   bst shell flatpak-autotools.bst hello

