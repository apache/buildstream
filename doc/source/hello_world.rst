

.. _hello_world:

Hello World
===========
This walkthrough aims to provide a new BuildStream user with an understanding of the following:

* The typical structure of a project.
  - Where to store `.bst` files.
  - Where to store sources.
* The purpose of the `project.conf` file.
* How to execute `bst` commands.

First we need to create a directory for the project and then initialise the project
with the `bst init` command. So, to create the project "helloWorld", we execute the
following::

  mkdir helloWorld
  cd helloWorld
  bst init --project-name helloWorld

This should produce the following output:

.. code:: bash

   Created project.conf at: /path/to/project/helloWorld/project.conf

Simply executing `ls` will show you that a `project.conf` file has been introduced
as well as an *elements* sub-directory.

The `project.conf` file contains the following:

.. code:: yaml

   # Unique project name
   name: helloWorld

   # Required BuildStream format version
   format-version: 8

   # Subdirectory where elements are stored
   element-path: elements

This file is in YAML format and, in this example, contains three attributes:

* `name:` The project name is a unique symbol for the project, thus is used to distinguish
  the project from others.
* `format-version:` The project's minimum required format version of BuildStream. This
  defaults to the latest version.
* `element-path`: The location of the elements (*.bst* files) relative to the project's
  root directory. This defaults to *elements* and we encourage users to adopt this method.

.. note::
   Further documentation describing the `project.conf` file can be found
   :ref:`here <projectconf>`.

As mentioned above, the *elements* sub-directory is where the elements (*.bst* files) are to
be stored. First, change into this directory::

  cd elements

Now, using a text editor of your choice, create a file named `hello.bst` and insert
the following content:

.. code:: yaml

   kind: import

   sources:
   - kind: local
     path: files/hello.world

   config:
     source: /
     target: /

The `kind:` attribute indicates the type of element this is, in this case, we are specifying
an *import* type element. To be more precise, this attribute specifies which plugin should
operate on the element's input, in order to produce its output. It is these plugins that
define element types and the BuildStream supported elements can be found :ref:`here <plugins>`.

An element's input is specified by the  `sources:` attribute. In our simple example, the input
will be a "local" file (`hello.world`) located at "*files/hello.world*" relative to the project's root.
A list of BuildStream-supported sources can be found :ref:`here <supported_sources>`.

The `config:` attribute allows us to configure the element itself. It should be noted that options
for this attribute will vary depending on the type (kind) of element. However, for our import element,
we take this 'local' directory, and take everything from its root directory and put it in the root
directory of the resulting artifact. I.e. We import the files/hello.world path as our *sysroot*.

.. note::

   Import elements are relatively simple as they directly import "artifacts" (built elements) from
   their source without any kind of processing.

Now that we have declared that we will be importing the `hello.world` file, we need to ensure
that this file actually exists for us to import. To do this, execute the following::

  mkdir files
  cd files
  touch hello.world

Executing `ls` will show that we have a file named `hello.world` in the *files* sub-directory.
Now, we can return to the project's root directory and initiate the pipeline::

  cd ..
  bst build hello.bst

This should produce an output similar to the following::

  [--:--:--][][] START   Build
  [--:--:--][][] START   Loading pipeline
  [00:00:00][][] SUCCESS Loading pipeline
  [--:--:--][][] START   Resolving pipeline
  [00:00:00][][] SUCCESS Resolving pipeline
  [--:--:--][][] START   Resolving cached state
  [00:00:00][][] SUCCESS Resolving cached state

  BuildStream Version 1.1.3+18.gf3be313a
    Session Start: Friday, 04-05-2018 at 14:50:27
    Project:       helloWorld (/pathway/to//helloWorld)
    Targets:       hello.bst

  User Configuration
    Configuration File:      /pathway/to/.config/buildstream.conf
    Log Files:               /pathway/to/.cache/buildstream/logs
    Source Mirrors:          /pathway/to/.cache/buildstream/sources
    Build Area:              /pathway/to/.cache/buildstream/build
    Artifact Cache:          /pathway/to/.cache/buildstream/artifacts
    Strict Build Plan:       Yes
    Maximum Fetch Tasks:     10
    Maximum Build Tasks:     2
    Maximum Push Tasks:      4
    Maximum Network Retries: 2

  Pipeline
     buildable ec690a278f57d5f56d3fc145a3e68ba34effb755f2036725962aaf1ac47d1e4d hello.bst 
  ===============================================================================
  [--:--:--][][] START   Checking sources
  [00:00:00][][] SUCCESS Checking sources
  [--:--:--][ec690a27][build:hello.bst  ] START   helloWorld/hello/ec690a27-build.10237.log
  [--:--:--][ec690a27][build:hello.bst  ] START   Staging sources
  [00:00:00][ec690a27][build:hello.bst  ] SUCCESS Staging sources
  [--:--:--][ec690a27][build:hello.bst  ] START   Caching artifact
  [00:00:00][ec690a27][build:hello.bst  ] SUCCESS Caching artifact
  [00:00:00][ec690a27][build:hello.bst  ] SUCCESS helloWorld/hello/ec690a27-build.10237.log
  [00:00:00][][] SUCCESS Build

  Pipeline Summary
    Total:       1
    Session:     1
    Fetch Queue: processed 0, skipped 1, failed 0 
    Build Queue: processed 1, skipped 0, failed 0 

Congratulations! You've just successfully executed a BuildStream pipeline.

