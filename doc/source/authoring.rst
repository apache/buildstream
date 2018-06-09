

Authoring projects
==================
This section details how to use the BuildStream YAML format to
create your own project or modify existing projects.


.. toctree::
   :maxdepth: 2
   :caption: Project format

   formatintro
   projectconf
   format
   public
   projectrefs


Plugins
-------
Plugins provide their own individual plugin specific YAML configurations,
The element ``.bst`` files can specify plugin specific configuration in
the :ref:`config section <format_config>`, while sources declared on a
given element specify their plugin specific configuration directly
:ref:`in their source declarations <format_sources>`.


General elements
~~~~~~~~~~~~~~~~
.. toctree::
   :maxdepth: 1

   elements/stack
   elements/import
   elements/compose
   elements/script
   elements/junction
   elements/filter


Build elements
~~~~~~~~~~~~~~
.. toctree::
   :maxdepth: 1

   elements/manual
   elements/make
   elements/autotools
   elements/cmake
   elements/qmake
   elements/distutils
   elements/makemaker
   elements/modulebuild
   elements/meson
   elements/pip


Sources
~~~~~~~
.. toctree::
   :maxdepth: 1

   sources/local
   sources/tar
   sources/zip
   sources/git
   sources/bzr
   sources/ostree
   sources/patch
   sources/deb


External plugins
----------------
External plugins need to be installed separately, here is
a list of BuildStream plugin projects known to us at this time:

* `bst-external <http://buildstream.gitlab.io/bst-external/>`_
