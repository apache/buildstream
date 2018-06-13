About
-----
.. image:: https://gitlab.com/BuildStream/buildstream/badges/master/pipeline.svg
   :target: https://gitlab.com/BuildStream/buildstream/commits/master

.. image:: https://gitlab.com/BuildStream/buildstream/badges/master/coverage.svg?job=coverage
   :target: https://gitlab.com/BuildStream/buildstream/commits/master


What is BuildStream?
====================
BuildStream is a Free Software tool for building/integrating software stacks.
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

  BuildStream provides a a flexible and extensible framework for the modelling
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


How do I use BuildStream?
=========================
Please refer to the `documentation <https://buildstream.gitlab.io/buildstream/>`_
for  information about installing BuildStream, and about the BuildStream YAML format
and plugin options.


How does BuildStream work?
==========================
BuildStream operates on a set of YAML files (.bst files), as follows:

* loads the YAML files which describe the target(s) and all dependencies
* evaluates the version information and build instructions to calculate a build
  graph for the target(s) and all dependencies and unique cache-keys for each
  element
* retrieves elements from cache if they are already built, or builds them in a
  sandboxed environment using the instructions declared in the .bst files
* transforms/configures and/or deploys the resulting target(s) based on the
  instructions declared in the .bst files.


How can I get started?
======================
The easiest way to get started is to explore some existing .bst files, for example:

* https://gitlab.gnome.org/GNOME/gnome-build-meta/
* https://gitlab.com/freedesktop-sdk/freedesktop-sdk
* https://gitlab.com/baserock/definitions
* https://gitlab.com/BuildStream/buildstream-examples/tree/master/build-x86image
* https://gitlab.com/BuildStream/buildstream-examples/tree/master/netsurf-flatpak

If you have any questions please ask on our `#buildstream <irc://irc.gnome.org/buildstream>`_ channel in `irc.gnome.org <irc://irc.gnome.org>`_

