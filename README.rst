BuildStream
-----------
What is BuildStream?
====================

BuildStream is an open-source tool for building/integrating software stacks,
similar to Bazel, BitBake, BuildRoot, Portage and Repo. It supports multiple
build-systems (e.g. make, cmake, cpan, qmake, autotools, distutils) and
multiple languages, and can create outputs in a range of package formats, for
multiple platforms and chipsets. 

Why should I use BuildStream?
=============================

BuildStream offers the following advantages:

**Declarative build definitions:** BuildStream provides a a flexible and extensible
framework for the modelling of build pipelines in a declarative YAML format,
written in python.

**Support for developer and integrator workflows:** BuildStream provides traceability
and reproducibility for integrators handling stacks of hundreds/thousands
of components, as well as workspace features and shortcuts to minimise cycle-time
for developers.

**Fast and predictable:** BuildStream can cache previous builds and track changes
to source file content and build/config commands. BuildStream only rebuilds the
things that have changed.

**Extensible:** You can extend BuildStream to support your favourite build-system.

**Bootstrap toolchains and bootable systems:** BuildStream can create full systems
and complete toolchains from scratch, for a range of ISAs including x86_32,
x86_64, ARMv7, ARMv8, MIPS.

How do I use BuildStream?
=========================

Please refer to the `complete documentation <https://buildstream.gitlab.io/buildstream/>`_
for  information about installing BuildStream, and about the BuildStream YAML format
and plugin options.

How does BuildStream work?
==========================

BuildStream processes a set of YAML files (.bst files):

- loads the set of YAML files which describe the target(s)
- evaluates the version information and build instructions to calculate a build
  graph for the target(s) and all dependencies and unique cache-keys for each
  element
- retrieves elements from cache if they are already built, or builds them using
  the instructions declared in the .bst files
- transforms and/or deploys the resulting target(s) based on the instructions
  declared in the .bst files.

How can I get started?
======================

The easiest way to get started is to explore some existing .bst files, for example:

- https://gitlab.gnome.org/GNOME/gnome-build-meta/
- https://gitlab.com/freedesktop-sdk/freedesktop-sdk
- https://gitlab.com/baserock/definitions
- https://gitlab.com/BuildStream/buildstream-examples/tree/x86image/build-x86image
- https://gitlab.com/BuildStream/buildstream-examples/tree/sam/netsurf

If you have any questions please ask on our `irc channel <irc://irc.gnome.org/buildstream>`_

