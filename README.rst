About
-----

.. image:: https://buildstream.gitlab.io/buildstream/_static/release.svg
   :target: https://gitlab.com/BuildStream/buildstream/commits/bst-1.2

.. image:: https://buildstream.gitlab.io/buildstream/_static/snapshot.svg
   :target: https://gitlab.com/BuildStream/buildstream/commits/master

.. image:: https://gitlab.com/BuildStream/buildstream/badges/master/pipeline.svg
   :target: https://gitlab.com/BuildStream/buildstream/commits/master

.. image:: https://gitlab.com/BuildStream/buildstream/badges/master/coverage.svg?job=coverage
   :target: https://gitlab.com/BuildStream/buildstream/commits/master

.. image:: https://img.shields.io/pypi/v/BuildStream.svg
   :target: https://pypi.org/project/BuildStream


What is BuildStream?
====================
`BuildStream <https://buildstream.build>`_ is a Free Software tool for 
building/integrating software stacks.
It takes inspiration, lessons and use-cases from various projects including
OBS, Reproducible Builds, Yocto, Baserock, Buildroot, Aboriginal, GNOME Continuous,
JHBuild, Flatpak Builder and Android repo.

BuildStream supports multiple build-systems (e.g. autotools, cmake, cpan, distutils,
make, meson, qmake), and can create outputs in a range of formats (e.g. debian packages,
flatpak runtimes, sysroots, system images) for multiple platforms and chipsets.


Why should I use BuildStream?
=============================
BuildStream offers the following advantages:

* **Declarative build instructions/definitions**

  BuildStream provides a flexible and extensible framework for the modelling
  of software build pipelines in a declarative YAML format, which allows you to
  manipulate filesystem data in a controlled, reproducible sandboxed environment.

* **Support for developer and integrator workflows**

  BuildStream provides traceability and reproducibility for integrators handling
  stacks of hundreds/thousands of components, as well as workspace features and
  shortcuts to minimise cycle-time for developers.

* **Fast and predictable**

  BuildStream can cache previous builds and track changes to source file content
  and build/config commands. BuildStream only rebuilds the things that have changed.

* **Extensible**

  You can extend BuildStream to support your favourite build-system.

* **Bootstrap toolchains and bootable systems**

  BuildStream can create full systems and complete toolchains from scratch, for
  a range of ISAs including x86_32, x86_64, ARMv7, ARMv8, MIPS.













Mission statement
=================

* **Deterministic build environment**

  Ideally, the build result (or *artifact*) of any given build will always be
  bit-for-bit identical if it is given exactly the same inputs, regardless of
  the host environment, so long as BuildStream supports the given host.

  To this end, we go to some lengths to ensure a clean execution environment
  for building, and we bump the core cache key version if ever we change or
  improve sanitizing of the execution environment, so that everything needs
  to be rebuilt.

  While BuildStream cannot itself guarantee a bit-for-bit identical result
  for every identical input, we can help in the majority of the work needed
  to ensure your builds are determinstic and reproducible.

* **Reusable build instructions**

  Our declarative format is designed with the intention that the same BuildStream
  project can be used to accomplish various things for the set of software it
  defines the integration for.

  For instance, using project options; it should be possible to reuse the same
  project to deploy the same software stack, or bundle, in various ways and
  on various platforms. This should be possible with BuildStream using only some
  conditional statements, with minimal redundance and maximum reuse.

* **Backwards compatibility**

  BuildStream provides various backwards compatible stable API surfaces, in this
  way we ensure that nobody's project can ever break as a result of upgrading to
  a new version of BuildStream.

  These stable API surfaces include:

  * The command line interface. BuildStream is intended to be scriptable and integratable
    into third party tooling. For this reason the command line interface may be extended
    from version to version but existing interfaces cannot be modified or removed.

  * The Python plugin facing API surface. In order to avoid breaking anyone's project
    who uses a custom or third party plugin, the plugin interfaces may be extended but
    can never be modified or removed.

  * The YAML format. As the main API surface for project authors, interfaces can be
    extended in the YAML format but never modified or removed.

  Beyond stability of the API surfaces, there is also the stability of the cache
  keys. Currently BuildStream guarantees that artifact cache keys will never change
  in a given stable release of BuildStream (e.g., all versions of 1.2.x will produce
  the same cache key for the same project).

  It is a long term goal to also make artifact cache keys stable, that any later version
  of BuildStream produces the same cache key for an artifact which was built by any other
  version of BuildStream

* **Build avoidance**

  It is a general goal to reduce builds as much as possible. Whenever we can
  guarantee that we already have a cached artifact which has identical inputs,
  we should always prefer the existing artifact.

* **Convenient developer experience**

  As an integration tool, we place focus on determinism first, but recognize that
  developers need to have the same guarantees of determinism as integrators do, but
  normally lack the tooling perform edit, compile and test cycles inside a well
  defined deterministic build environment.

  BuildStream aims to bring the deterministic and predictable target system
  environment to the developer's fingertips, while also bringing convinent
  developer tools to the integrator.

* **Decoupling of tooling and payload**

  BuildStream is a generic build and integration tool which does not make any
  assumptions about which software platform or machine architecture is going to
  be used.

  Some plugin elements invoking platform specific tooling such as autotools or
  cmake, these provide configurable defaults for and are designed with maximum
  configurability in mind, while the core application should not become biased
  towards specific platforms.

* **Project Modularity**

  From various experiences with tooling used to produce customized Linux based
  appliances, we have recognized a trend that is to combine all build metadata
  for the whole stack (from kernel to the user facing applications) in a single
  repository, we see this as problematic as it does not allow inter-organizational
  knowledge sharing easily, or separation of teams which produce and maintain separate
  parts of the operating system stack.

  BuildStream aims to make it easier to produce and maintain systems in a modular
  fashion, where organizations or teams can maintain and share parts of the stack.

* **Easy to use**

  Part of the mission is to be well documented, and as simple and straightforward
  to use as possible.

  As a part of this, we place great emphasis on error reporting, and try to fail
  as early as possible when we know that we can fail; and provide as much useful
  context to the user as possible to allow them to easily figure out what went
  wrong.

* **Core simplicity, maximum flexibility**

  BuildStream aims to be a generic core which simply processes an abstract pipeline
  of elements which perform filesystem permutations inside a sandboxed environment.

  We address the problem of scope creep in the following ways:

  - **Many simple tools exposed in the CLI**

    The command line interface is composed mostly of simple commands which
    are API stable.

    In this way we allow more complex and user specific constructs to be implemented
    as shell scripts which invoke BuildStream one or more times, instead of growing
    user specific features directly in the BuildStream CLI.

  - **Stable Plugin API**

    By providing a stable plugin API with strong guarantees that BuildStream will
    not break external plugins, we hope to encourage and develop a healthy ecosystem
    of useful plugins which users can reliably use in their project.


How do I use BuildStream?
=========================
Please refer to the `documentation <https://buildstream.gitlab.io/buildstream/>`_
for  information about installing BuildStream, and about the BuildStream YAML format
and plugin options.


How does BuildStream work?
==========================
BuildStream operates on a set of YAML files (.bst files), as follows:

* Loads the YAML files which describe the target(s) and all dependencies.
* Evaluates the version information and build instructions to calculate a build
  graph for the target(s) and all dependencies and unique cache-keys for each
  element.
* Retrieves previously built elements (artifacts) from a local/remote cache, or
  builds the elements in a sandboxed environment using the instructions declared
  in the .bst files.
* Transforms/configures and/or deploys the resulting target(s) based on the
  instructions declared in the .bst files.


How can I get started?
======================
To get started, first `install BuildStream by following the installation guide
<https://buildstream.gitlab.io/buildstream/main_install.html>`_
and then follow our tutorial in the
`user guide <https://buildstream.gitlab.io/buildstream/main_using.html>`_.

We also recommend exploring some existing BuildStream projects:

* https://gitlab.gnome.org/GNOME/gnome-build-meta/
* https://gitlab.com/freedesktop-sdk/freedesktop-sdk
* https://gitlab.com/baserock/definitions

If you have any questions please ask on our `#buildstream <irc://irc.gnome.org/buildstream>`_ channel in `irc.gnome.org <irc://irc.gnome.org>`_
