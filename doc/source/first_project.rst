:orphan:

.. _first_project:

Your first project: HelloWorld
==============================

This is a minimal example of a BuildStream project::

  $ echo "name: Hello.World" > project.conf
  $ touch hello.world
  $ cat hello.bst 
  kind: import
  sources:
  - kind: local
    path: hello.world
  config:
    source: /
    target: /

  $ bst build hello.bst 
  [--:--:--][][] START   Loading pipeline
  [00:00:00][][] SUCCESS Loading pipeline
  [--:--:--][][] START   Resolving pipeline
  [00:00:00][][] SUCCESS Resolving pipeline
  [--:--:--][][] START   Resolving cached state
  [00:00:00][][] SUCCESS Resolving cached state

  BuildStream Version 1.1.2.dev4+g7fdddf3
    Session Start: Thursday, 08-03-2018 at 16:53:34
    Project:       Hello.World (/src)
    Targets:       hello.bst

  User Configuration
    Configuration File:      Default Configuration
    Log Files:               /root/.cache/buildstream/logs
    Source Mirrors:          /root/.cache/buildstream/sources
    Build Area:              /root/.cache/buildstream/build
    Artifact Cache:          /root/.cache/buildstream/artifacts
    Maximum Fetch Tasks:     10
    Maximum Build Tasks:     4
    Maximum Push Tasks:      4
    Maximum Network Retries: 2

  Pipeline
    buildable b4f6a94f hello.bst 
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  [--:--:--][][] START   Checking sources
  [00:00:00][][] SUCCESS Checking sources
  [--:--:--][][] START   Starting build
  [--:--:--][b4f6a94f][build:hello.bst  ] START   root/.cache/buildstream/logs/Hello.World/hello/b4f6a94f-build.607.log
  [--:--:--][b4f6a94f][build:hello.bst  ] START   Staging sources
  [00:00:00][b4f6a94f][build:hello.bst  ] SUCCESS Staging sources
  [--:--:--][b4f6a94f][build:hello.bst  ] START   Caching Artifact
  [00:00:00][b4f6a94f][build:hello.bst  ] SUCCESS Caching Artifact
  [00:00:00][b4f6a94f][build:hello.bst  ] SUCCESS root/.cache/buildstream/logs/Hello.World/hello/b4f6a94f-build.607.log
  [00:00:00][][] SUCCESS Build Complete

  Pipeline Summary
    Total:       1
    Session:     1
    Fetch Queue: processed 0, skipped 1, failed 0 
    Build Queue: processed 1, skipped 0, failed 0 

  $ bst checkout hello.bst my-output
  [--:--:--][][] START   Loading pipeline
  [00:00:00][][] SUCCESS Loading pipeline
  [--:--:--][][] START   Resolving pipeline
  [00:00:00][][] SUCCESS Resolving pipeline
  [--:--:--][][] START   Resolving cached state
  [00:00:00][][] SUCCESS Resolving cached state
  [--:--:--][][] START   Staging dependencies
  [00:00:00][][] SUCCESS Staging dependencies
  [--:--:--][][] START   Integrating sandbox
  [00:00:00][][] SUCCESS Integrating sandbox
  [--:--:--][][] START   Checking out files in my-output
  [00:00:00][][] SUCCESS Checking out files in my-output

  $ ls my-output/
  hello.world
