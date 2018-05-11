
.. _examples:

Examples
========
This page contains documentation for real examples of BuildStream projects,
described step by step. All run under CI, so you can trust they are
maintained and work as expected.

for detail info go to :ref:`authoring`.

-----

Using flatpak runtimes to build and run from source

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

