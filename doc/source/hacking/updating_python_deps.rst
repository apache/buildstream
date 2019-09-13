

.. _updating_python_deps:

Updating BuildStream's Python dependencies
------------------------------------------
BuildStream's Python dependencies are listed in multiple
`requirements files <https://pip.readthedocs.io/en/latest/reference/pip_install/#requirements-file-format>`_
present in the ``requirements`` directory.

All ``.txt`` files in this directory are generated from the corresponding
``.in`` file, and each ``.in`` file represents a set of dependencies. For
example, ``requirements.in`` contains all runtime dependencies of BuildStream.
``requirements.txt`` is generated from it, and contains pinned versions of all
runtime dependencies (including transitive dependencies) of BuildStream.

When adding a new dependency to BuildStream, or updating existing dependencies,
it is important to update the appropriate requirements file accordingly. After
changing the ``.in`` file, run the following to update the matching ``.txt``
file::

   make -C requirements
