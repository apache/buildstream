

.. _managing_data_files:

Managing data files
-------------------
When adding data files which need to be discovered at runtime by BuildStream, update setup.py accordingly.

When adding data files for the purpose of docs or tests, or anything that is not covered by
setup.py, update the MANIFEST.in accordingly.

At any time, running the following command to create a source distribution should result in
creating a tarball which contains everything we want it to include::

  ./setup.py sdist
