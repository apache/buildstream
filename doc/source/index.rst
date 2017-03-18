.. BuildStream documentation master file, created by
   sphinx-quickstart on Mon Nov  7 21:03:37 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. toctree::
   :maxdepth: 2

BuildStream Documentation
=========================

About BuildStream
-----------------
BuildStream is a flexible and extensible framework for the modelling of build
pipelines in a declarative YAML format, written in python.

BuildStream defines a pipeline as abstract elements related by their dependencies,
and stacks to conveniently group dependencies together. Basic element types for
importing SDKs in the form of tarballs or ostree checkouts, building software
components and exporting SDKs or deploying bootable filesystem images will be
included in BuildStream, but it is expected that projects forge their own custom
elements for doing more elaborate things such as deploying software in special ways.


Using BuildStream
=================
Here are some resources to help you get off the ground when creating your very
first BuildStream project.

* :ref:`format`


Elements
--------


General Elements
~~~~~~~~~~~~~~~~

* :mod:`stack` - Symbolic Element for dependency grouping
* :mod:`import` - Import sources directly
* :mod:`compose` - Compose the output of multiple elements
* :mod:`script` - Run scripts to create output

Build Elements
~~~~~~~~~~~~~~

* :mod:`manual` - Manual Build Element
* :mod:`autotools` - Autotools Build Element
* :mod:`cmake` - CMake Build Element
* :mod:`qmake` - QMake Build Element
* :mod:`distutils` - Python Distutils Build Element
* :mod:`makemaker` - Perl MakeMaker Build Element
* :mod:`modulebuild` - Perl Module::Build Build Element
* :mod:`meson` - Meson Build Element


Sources
--------
The following source types are provided with BuildStream:

* :mod:`local` - A Source implementation local files and directories
* :mod:`git` - A Source implementation for git
* :mod:`ostree` - A Source implementation for ostree


Core Framework
--------------
The core public APIs are of interest to anyone who wishes to
implement custom :mod:`Element <buildstream.element>` or
:mod:`Source <buildstream.source>` plugins.

* :mod:`Plugin <buildstream.plugin>` - Base Class for all plugins
* :mod:`Source <buildstream.source>` - Base Source Class
* :mod:`Element <buildstream.element>` - Base Element Class
* :mod:`BuildElement <buildstream.buildelement>` - Build Element Class
* :mod:`Context <buildstream.context>` - Invocation Context
* :mod:`Project <buildstream.project>` - Loaded Project
* :mod:`Sandbox <buildstream.sandbox>` - Build Sandbox
* :mod:`Utilities <buildstream.utils>` - Utilities for Plugins


Indices and tables
------------------
* :ref:`modindex`
* :ref:`genindex`
