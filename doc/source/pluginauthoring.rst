.. _pluginauthoring:


Authoring Plugins
=================
Here we try to provide any additional documentation one will need
to create their own custom plugins to use with BuildStream.


.. _core_framework:

Core Framework
--------------
The core public APIs are of interest to anyone who wishes to
implement custom :mod:`Element <buildstream.element>` or
:mod:`Source <buildstream.source>` plugins.

* :mod:`Plugin <buildstream.plugin>` - Base Class for all plugins
* :mod:`Source <buildstream.source>` - Base Source Class
* :mod:`Element <buildstream.element>` - Base Element Class
* :mod:`BuildElement <buildstream.buildelement>` - Build Element Class
* :mod:`ScriptElement <buildstream.scriptelement>` - Script Element Class
* :mod:`Context <buildstream.context>` - Invocation Context
* :mod:`Project <buildstream.project>` - Loaded Project
* :mod:`Sandbox <buildstream.sandbox.sandbox>` - Build Sandbox
* :mod:`Utilities <buildstream.utils>` - Utilities for Plugins
