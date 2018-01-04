.. BuildStream documentation master file, created by
   sphinx-quickstart on Mon Nov  7 21:03:37 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. toctree::
   :maxdepth: 2
   :hidden:

   modules

BuildStream Documentation
=========================

About BuildStream
-----------------
BuildStream is a flexible and extensible framework for the modelling of build
pipelines in a declarative YAML format, written in python.

These pipelines are composed of abstract elements which perform mutations on
on *filesystem data* as input and output, and are related to eachother by their
dependencies.


Installing
----------
* :ref:`installing`
* :ref:`docker`
* :ref:`artifacts`


Running
-------
* :ref:`invoking`
* :ref:`config`


Project format
--------------
* :ref:`formatintro`

  * :ref:`format_structure`
  * :ref:`format_composition`
  * :ref:`format_directives`

* :ref:`projectconf`

  * :ref:`project_essentials`
  * :ref:`project_options`
  * :ref:`project_defaults`
  * :ref:`project_builtin_defaults`

* :ref:`format`

  * :ref:`format_basics`
  * :ref:`format_dependencies`
  * :ref:`format_variables`

* :ref:`public`


Builtin Plugins
---------------
* :ref:`plugins`

  * :ref:`plugins_elements`
  * :ref:`plugins_sources`

External Plugins
----------------

* `bst-external <http://buildstream.gitlab.io/bst-external/>`_


Creating Plugins
----------------
* :ref:`pluginauthoring`

  * :ref:`core_framework`


Internals
---------
* :ref:`cachekeys`


Indices and tables
------------------
* :ref:`modindex`
* :ref:`genindex`
