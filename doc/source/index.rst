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
and CI pipelines in a declarative YAML format, written in python.

BuildStream defines a pipeline as abstract elements related by their dependencies,
and stacks to conveniently group dependencies together. Basic element types for
importing SDKs in the form of tarballs or ostree checkouts, building software
components and exporting SDKs or deploying bootable filesystem images will be
included in BuildStream, but it is expected that projects forge their own custom
elements for doing more elaborate things such as running custom CI tests or deploying
software in special ways.


Core Framework
--------------

* :class:`~buildstream.context.Context` - Invocation Context
* :class:`~buildstream.element.Element` - Base Element Class
* :class:`~buildstream.source.Source` - Base Source Class


Plugins
-------

Elements
~~~~~~~~

* :class:`~build.BuildElement` - Abstract Software Building Element

Sources
~~~~~~~

* :class:`~git.GitSource` - A Source implementation for git


Indices and tables
------------------
* :ref:`modindex`
* :ref:`genindex`
