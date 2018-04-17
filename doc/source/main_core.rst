

.. _main_core:

Core documentation and reference
================================
This section details the core API reference along with
other more elaborate details about BuildStream internals.


.. _core_framework:

Core framework
--------------
The core public APIs are of interest to anyone who wishes to
implement custom :mod:`Element <buildstream.element>` or
:mod:`Source <buildstream.source>` plugins, and can also be
useful for working on BuildStream itself.

* :mod:`Plugin <buildstream.plugin>` - Base Class for all plugins
* :mod:`Source <buildstream.source>` - Base Source Class
* :mod:`Element <buildstream.element>` - Base Element Class
* :mod:`BuildElement <buildstream.buildelement>` - Build Element Class
* :mod:`ScriptElement <buildstream.scriptelement>` - Script Element Class
* :mod:`Sandbox <buildstream.sandbox.sandbox>` - Build Sandbox
* :mod:`Utilities <buildstream.utils>` - Utilities for Plugins


Internals
---------
.. toctree::
   :maxdepth: 2

   modules
