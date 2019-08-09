
.. _plugins:

Plugin specific documentation
=============================
Plugins provide their own individual plugin specific YAML configurations,
The element ``.bst`` files can specify plugin specific configuration in
the :ref:`config section <format_config>`, while sources declared on a
given element specify their plugin specific configuration directly
:ref:`in their source declarations <format_sources>`.


General elements
----------------
.. toctree::
   :maxdepth: 1

   elements/stack
   elements/import
   elements/compose
   elements/script
   elements/junction
   elements/filter


.. _plugins_build_elements:

Build elements
--------------
.. toctree::
   :maxdepth: 1

   elements/manual
   elements/autotools
   elements/qmake
   elements/distutils
   elements/makemaker
   elements/modulebuild
   elements/pip


.. _plugins_sources:

Sources
-------
.. toctree::
   :maxdepth: 1

   sources/local
   sources/remote
   sources/tar
   sources/zip
   sources/git
   sources/bzr
   sources/patch
   sources/deb
   sources/pip


External plugins
----------------
External plugins need to be installed separately, here is
a list of BuildStream plugin projects known to us at this time:

* `bst-plugins-experimental <http://buildstream.gitlab.io/bst-plugins-experimental/>`_
* `bst-plugins-container <https://pypi.org/project/bst-plugins-container/>`_
