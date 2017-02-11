BuildStream
===========

BuildStream is a flexible and extensible framework for the modelling of build
and CI pipelines in a declarative YAML format, written in python.

BuildStream defines a pipeline as abstract elements related by their dependencies,
and stacks to conveniently group dependencies together. Basic element types for
importing SDKs in the form of tarballs or ostree checkouts, building software
components and exporting SDKs or deploying bootable filesystem images will be
included in BuildStream, but it is expected that projects forge their own custom
elements for doing more elaborate things such as running custom CI tests or deploying
software in special ways.

The build pipeline is a flow based concept which operates on filesystem data as
input and output. An element's input is the sum of its dependencies, sources and
configuration loaded from the YAML, while the output is something on the filesystem
which another element can then depend on.
