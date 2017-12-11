.. _plugins:

Plugins
=======


.. _plugins_elements:

Elements
--------
The following element types are provided with BuildStream:


General Elements
~~~~~~~~~~~~~~~~

* :mod:`stack <elements.stack>` - Symbolic Element for dependency grouping
* :mod:`import <elements.import>` - Import sources directly
* :mod:`compose <elements.compose>` - Compose the output of multiple elements
* :mod:`script <elements.script>` - Run scripts to create output

.. _plugins_build:

Build Elements
~~~~~~~~~~~~~~

* :mod:`manual <elements.manual>` - Manual Build Element
* :mod:`autotools <elements.autotools>` - Autotools Build Element
* :mod:`cmake <elements.cmake>` - CMake Build Element
* :mod:`qmake <elements.qmake>` - QMake Build Element
* :mod:`distutils <elements.distutils>` - Python Distutils Build Element
* :mod:`makemaker <elements.makemaker>` - Perl MakeMaker Build Element
* :mod:`modulebuild <elements.modulebuild>` - Perl Module::Build Build Element
* :mod:`meson <elements.meson>` - Meson Build Element
* :mod:`pip <elements.pip>` - Pip build element


.. _plugins_sources:


Sources
--------
The following source types are provided with BuildStream:

* :mod:`local <sources.local>` - A Source implementation for local files and directories
* :mod:`tar <sources.tar>` - A Source implementation for tarballs
* :mod:`zip <sources.zip>` - A Source implementation for zip archives
* :mod:`git <sources.git>` - A Source implementation for git
* :mod:`bzr <sources.bzr>` - A Source implementation for bazaar
* :mod:`ostree <sources.ostree>` - A Source implementation for ostree
* :mod:`patch <sources.patch>` - A Source implementation for applying local patches
