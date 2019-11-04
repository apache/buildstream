About
-----

.. image:: https://buildstream.gitlab.io/buildstream/_static/release.svg
   :target: https://gitlab.com/BuildStream/buildstream/commits/bst-1

.. image:: https://buildstream.gitlab.io/buildstream/_static/snapshot.svg
   :target: https://gitlab.com/BuildStream/buildstream/commits/master

.. image:: https://gitlab.com/BuildStream/buildstream/badges/master/pipeline.svg
   :target: https://gitlab.com/BuildStream/buildstream/commits/master

.. image:: https://gitlab.com/BuildStream/buildstream/badges/master/coverage.svg?job=coverage
   :target: https://gitlab.com/BuildStream/buildstream/commits/master

.. image:: https://img.shields.io/pypi/v/BuildStream.svg
   :target: https://pypi.org/project/BuildStream

.. image:: https://app.fossa.io/api/projects/git%2Bgitlab.com%2FBuildStream%2Fbuildstream.svg?type=shield
   :target: https://app.fossa.io/projects/git%2Bgitlab.com%2FBuildStream%2Fbuildstream?ref=badge_shield


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


How do I use BuildStream?
=========================
Please refer to the `documentation <https://docs.buildstream.build>`_
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
<https://buildstream.build/install.html>`_
and then follow our tutorial in the
`user guide <https://docs.buildstream.build/1.4.1/main_using.html>`_.

We also recommend exploring some existing BuildStream projects:

* https://gitlab.gnome.org/GNOME/gnome-build-meta/
* https://gitlab.com/freedesktop-sdk/freedesktop-sdk
* https://gitlab.com/baserock/definitions

If you have any questions please ask on our `#buildstream <irc://irc.gnome.org/buildstream>`_ channel in `irc.gnome.org <irc://irc.gnome.org>`_


Availability in distros
=======================
* BuildStream:

.. image:: https://repology.org/badge/vertical-allrepos/buildstream.svg
   :target: https://repology.org/metapackage/buildstream/versions

* BuildStream external plugins (bst-external)

.. image:: https://repology.org/badge/vertical-allrepos/bst-external.svg
   :target: https://repology.org/metapackage/bst-external/versions
