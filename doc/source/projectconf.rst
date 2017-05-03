.. _projectconf:


Project Configuration
=====================
The project configuration file should be named ``project.conf`` and
be located at the project root. It holds information such as Source
aliases relevant for the sources used in the given project as well as
overrides for the configuration of element types used in the project.

Values specified in the project configuration override any of the
default BuildStream project configuration, which is included here
for reference and includes comments describing all of the possible
configuration values:

  .. literalinclude:: ../../buildstream/data/projectconfig.yaml
     :language: yaml
