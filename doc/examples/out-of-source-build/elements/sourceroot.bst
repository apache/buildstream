depends:
- base.bst
description: |2

  Hello world example from cmake
kind: cmake
sources:
- kind: local
  path: files/OutOfSourceProject
  directory: Source
variables:
  command-subdir: build
  conf-root: "%{build-root}/Source/"

