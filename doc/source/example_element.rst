
.. _example_element:

An example build element
========================
At the core of all BuildStream projects are the elements, of which, there are various types.
A list of BuildStream-supported element types can be found :ref:`here <elements>`.

Build elements contain "instructions" detailing what we should do with said element (e.g.
how it should be built, or where it should be imported from), as well
as detailing the *dependencies* - elements that are required to be integrated into the sandbox
before the build of the target element.

Below is an example build element from the
`GNOME <https://gitlab.gnome.org/GNOME/gnome-build-meta/tree/master>`_ project which describes
how to build the `gedit <https://wiki.gnome.org/Apps/Gedit>`_ text editor:

.. code:: yaml

   kind: autotools
   sources:
   - kind: git
     url: git_gnome_org:gedit
     track: master
     submodules:
       libgd:
	 url: git_gnome_org:libgd
   depends:
   - core-deps/gspell.bst
   - core-deps/gtksourceview-3.bst
   - core-deps/libpeas.bst
   - core-deps/yelp-tools.bst
   - core/adwaita-icon-theme.bst
   - core/gsettings-desktop-schemas.bst
   - base.bst


The "kind" attribute
--------------------
Notice that the above file contains no explicit build instructions. This is because gedit
uses a standard build system, autotools, which is supported by BuildStream.

The `kind` attribute instructs BuildStream that it should fill in the build instructions for this element
using the autotools element plugin. Other "kinds" of BuildStream supported build systems
can be found :ref:`here <build_elements>`.


The "sources" attribute
-----------------------
In the above example, the `sources` attribute references an upstream git repo (`kind: git`), which can
be cloned from the url declared by the `url` attribute. Notice that the url here does not look like a
conventional url. This is because it is using an alias which is defined in the `project.conf` of
the project. Thus, in the `project.conf` of this project, we would find:

.. code:: yaml
	  
   # Source aliases.
   #
   # These are used in the individual element.bst files in
   # place of specifying full uris.
   # 
   # The location from where source code is downloaded can
   # be changed without triggering a rebuild.
   #
   aliases:
     git_gnome_org: https://git.gnome.org/browse/

The `track:` attribute specifies which trcking branch or tag we should use to update the "ref"
when initiating the build pipeline.

BuildStream supports many other types of sources, a list of which can be found
:ref:`here <supported_sources>`.


The "depends" attribute
-----------------------
The `depends` attribute lists the filenames of other elements within the same project. The elements
listed here are required to be built before the build of *gedit*, thus making them *dependencies*.


.. note::

   The complete documentation detailing the various possible attributes of an element can
   be found :ref:`here <format>`.
