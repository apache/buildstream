:orphan:

.. _main_quickstart:

What is BuildStream?
====================
BuildStream is a command-line tool that executes software build and integration pipelines.

It supports a wide range of use cases: currently you can produce Debian packages, 
Linux virtual machine images, and Flatpak application bundles,
and it's possible to extend BuildStream through its plugin system to produce any type of 
output you like.

All builds are performed in a controlled sandbox with an emphasis on reproducibility. 
In particular, builds are not allowed to do network access within the sandbox.
This allows build results to be shared between multiple developers.

BuildStream does not mandate that you use any particular automation tool, but builds
can easily be automated using GitLab CI, Jenkins, BuildBot or with many other tools.

Concepts
--------
The bst commandline tool operates within a project and a project contains one or more elements.
The elements each describe how to build one component from its sources.

Projects can be small or large, and can depend on other BuildStream projects. 
We recommend keeping each BuildStream project in its own Git repository.

A project is marked by a project.conf file which sets up project-wide configuration options.
The syntax used is YAML. 
The directory containing project.conf is considered to be the top-level project directory,
and you must always run bst commands from this directory.

Elements usually live a subdirectory of the project named elements.
Each element is represented on disk by a .bst file which again uses YAML syntax.
An element has various attributes that authors can control, but BuildStream aims to support 
the "don't repeat yourself" principle and so provide sensible default values are provided that
should fit many cases.

Here is an example element, which is taken from the Freedesktop SDK project and describes
how to build the GNU Nano text editor::

  kind: autotools
  description: GNU nano

  depends:
    - filename: bootstrap-import.bst
      type: build
    - filename: base/pkg-config.bst

  sources:
    - kind: tar
      url: http://ftp.gnu.org/gnu/nano/nano-2.8.7.tar.xz
      ref: fbe31746958698d73c6726ee48ad8b0612697157961a2e9aaa83b4aa53d1165a

You can see at a glance that the upstream source tarball is referenced in the sources section.
Note that the ref field here stores the SHA256 checksum of the contents of the file,
which BuildStream uses to validate the tarball after fetching it.
The source declares that is of kind: tar. BuildStream supports various other types of sources too.
The list of built-in sources can be found here. Support for more types of source can be added by 
writing plugins.

There are no build instructions written here because GNU Nano uses a standard build system
that BuildStream already supports. The first line (kind: autotools) instructs BuildStream
that it should fill in the build instructions for this element using the autotools element plugin.
There are various ways to override the defaults which are described in the "Composition"
section of the reference manual.

The depends section is a little harder to read at a glance. The filenames listed here are
other elements within the same project. One of these provides the pkg-config tool which is built
in a similar way. The other provides a binary sysroot which is built as part of a separate project.
BuildStream runs all builds inside a sandbox without any access to the host, and it doesn't provide
any standard way of making standard programs like a UNIX Shell available in the sandbox.
All build commands require various tools to function, at minimal a shell but usually also a C compiler
and a whole array of other possible tools. It is up to the individual project to provide these,
and so the first element of a project will normally be an import element that pulls prebuilt
binaries from somewhere. 
