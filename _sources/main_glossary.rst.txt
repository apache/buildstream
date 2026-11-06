..
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.



Glossary
========

.. glossary::
   :sorted:


   ``.bst`` file
       The configuration for an :term:`Element <Element>`, represented
       in YAML format.


   Artifact
       The output collected after building an :term:`Element`.

       Artifacts can be built from :term:`Sources <Source>`, or pulled from a
       :term:`Remote Cache <Remote Cache>`, if available.

   Artifact name
       The :ref:`name of an artifact <artifact_names>`, which can be used
       in various commands to operate directly on artifacts, without requiring
       the use of a :term:`Project`.

   Cache
       BuildStream leverages various caching techniques in order to avoid
       duplicating work.

       Depending on context, "Cache" might refer to BuildStream's :term:`local
       cache <Local Cache>` or a :term:`Remote Cache <Remote Cache>`.


   Core plugin
       A :term:`Plugin <Plugin>` that is contained in the BuildStream
       package.  These are built-in and don't need to be defined in the
       project configuration.

       See :ref:`plugin documentation <plugins>` for more details on core
       plugins.


   Dependency
       :term:`Elements <Element>` in a BuildStream project can depend
       on other elements from the same project. The element dependent upon is
       called a dependency.

       See :ref:`Dependencies document <format_dependencies>` for more
       details.

   Dependency configuration
       Additional custom YAML configuration which is used to define
       an :term:`Element's <Element>` relationship with it's :term:`Dependency <Dependency>`.

       This is supported on limited :term:`Element <Element>` implementations, and
       each :term:`Element <Element>` defines what configuration it supports.

       See the :ref:`dependency documentation <format_dependencies>` for details
       on dependency configuration.

   Element
       An atom of a :term:`BuildStream project <Project>`. Projects consist of
       zero or more elements.

       During the build process, BuildStream transforms :term:`Sources
       <Source>` and :term:`Dependencies <Dependency>` of an
       element into its output. The output is called an
       :term:`Artifact <Artifact>`.

       Configuration for elements is stored in form of :term:`.bst files
       <.bst file>`. See :ref:`Declaring Elements document <format_basics>`
       for more details on element configurtion.


   External Plugin
       A :term:`Plugin <Plugin>` that is defined in some package other
       than BuildStream.

       External plugins must be declared in :ref:`the project configuration
       <project_plugins>`.

       For a list of known external plugin repositories, see
       :ref:`plugins_external`.


   Junction
       A special kind of :term:`Element <Element>`, that allows you to
       depend on elements from another project.

       See :mod:`Junction reference <elements.junction>` for details on how to
       configure junction elements.

       See :ref:`Junction guide <junction_elements>` for details on how to use
       junction elements.


   Local Cache
       To avoid duplicating work, BuildStream will cache sources, artifacts,
       logs, buildtrees etc. in a local cache directory. If these sources or
       artifacts are needed another time, BuildStream will use them from the
       cache.

       See :ref:`Local cache expiry <config_local_cache>` section of the user
       guide for details on how to configure the local cache.


   Plugin
       BuildStream Plugins define types of :term:`Elements <Element>`
       and :term:`Sources <Source>`. Hence, they come in two distinct
       varities - Element Plugins and Source Plugins.

       BuildStream supports some plugins :term:`out of the box
       <Core plugin>`. It also has support for :term:`third party
       plugins <External Plugin>`.


   Project
       A collection of :term:`Elements <Element>`.

       Elements in a project share some central configuration. See
       :ref:`projectconf` to learn how to configure BuildStream projects.


   Remote Cache
       A server setup for sharing BuildStream :term:`Sources <Source>`
       and/or :term:`Artifacts <Artifact>`.

       See :ref:`cache server documentation <cache_servers>` for details on
       artifact caches.


   Source
       Sources describe the input to the build of an :term:`Element`.

       In general, an element can have zero or more sources. But, certain
       element plugins may restrict the number of allowed sources.

       Sources are defined in the :ref:`Sources <format_sources>` section of
       :term:`Element <Element>` configuration.


   Subproject
       Subprojects are :term:`projects <Project>` which are referred
       to by a :term:`Junction`.


   Workspace
       Workspaces allow building one or more elements using a local, and
       potentially modified, copy of their sources.

       See :ref:`Workspaces guide <developing_workspaces>` for more details on
       how to use workspaces.
