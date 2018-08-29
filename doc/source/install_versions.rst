

.. _install_semantic_versioning:

Semantic Versioning
===================
BuildStream follows the Semantic Versioning Convention `(SemVer) <https://semver.org/>`_,
and uses even minor point numbers to denote releases intended for users while
odd minor point numbers represent development snapshops.

For example, for a given version number ``X.Y.Z``
 * The ``X.<even number>.*`` versions are releases intended for users.
 * The ``X.<odd number>.*`` versions are development spanshots intended for testing.

If you are :ref:`installing from git <install_git_checkout>`, please look for the latest
tag to ensure you're getting the latest release.

* Latest release:

  .. include:: release-badge.rst

* Latest development snapshot:

  .. include:: snapshot-badge.rst
