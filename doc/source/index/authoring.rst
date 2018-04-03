

.. _main_authoring:

Authoring Projects
==================
This section details how to use the BuildStream YAML format to
create your own project or modify existing projects.


.. toctree::
   :maxdepth: 2
   :caption: Project format

   authoring/formatintro
   authoring/projectconf
   authoring/format
   authoring/public
   authoring/projectrefs


Plugins
-------
Plugins provide their own individual plugin specific YAML configurations,
The element ``.bst`` files can specify plugin specific configuration in
the :ref:`config section <format_config>`, while sources declared on a
given element specify their plugin specific configuration directly
:ref:`in their source declarations <format_sources>`.


Elements
~~~~~~~~
The following element types are provided with BuildStream:


General Elements
''''''''''''''''

* :mod:`stack <elements.stack>` - Symbolic Element for dependency grouping
* :mod:`import <elements.import>` - Import sources directly
* :mod:`compose <elements.compose>` - Compose the output of multiple elements
* :mod:`script <elements.script>` - Run scripts to create output
* :mod:`junction <elements.junction>` - Integrate subprojects
* :mod:`filter <elements.filter>` - Extract a subset of files from another element


Build Elements
''''''''''''''

* :mod:`manual <elements.manual>` - Manual Build Element
* :mod:`autotools <elements.autotools>` - Autotools Build Element
* :mod:`cmake <elements.cmake>` - CMake Build Element
* :mod:`qmake <elements.qmake>` - QMake Build Element
* :mod:`distutils <elements.distutils>` - Python Distutils Build Element
* :mod:`makemaker <elements.makemaker>` - Perl MakeMaker Build Element
* :mod:`modulebuild <elements.modulebuild>` - Perl Module::Build Build Element
* :mod:`meson <elements.meson>` - Meson Build Element
* :mod:`pip <elements.pip>` - Pip build element


Sources
~~~~~~~
The following source types are provided with BuildStream:

* :mod:`local <sources.local>` - A Source implementation for local files and directories
* :mod:`tar <sources.tar>` - A Source implementation for tarballs
* :mod:`zip <sources.zip>` - A Source implementation for zip archives
* :mod:`git <sources.git>` - A Source implementation for git
* :mod:`bzr <sources.bzr>` - A Source implementation for bazaar
* :mod:`ostree <sources.ostree>` - A Source implementation for ostree
* :mod:`patch <sources.patch>` - A Source implementation for applying local patches
* :mod:`deb <sources.deb>` - A Source implementation for deb packages


External Plugins
----------------
External plugins need to be installed separately, here is
a list of BuildStream plugin projects known to us at this time:

* `bst-external <http://buildstream.gitlab.io/bst-external/>`_
