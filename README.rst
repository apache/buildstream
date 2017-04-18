BuildStream
===========
BuildStream is a flexible and extensible framework for the modelling of build
pipelines in a declarative YAML format, written in python.

These pipelines are composed of abstract elements which perform mutations on
on *filesystem data* as input and output, and are related to eachother by their
dependencies.

Basic element types for importing SDKs in the form of tarballs or ostree checkouts,
building software components and exporting SDKs or deploying bootable filesystem images
will be included in BuildStream, but it is expected that projects forge their own custom
elements for doing more elaborate things such as deploying software in special ways.

Documentation
-------------
Please refer to the `complete documentation <https://buildstream.gitlab.io/buildstream/>`_
for more information about installing BuildStream, and about the BuildStream YAML format
and plugin options.
