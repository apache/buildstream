depends:
- base.bst
description: |2

  Hello world example from automake
kind: autotools
sources:
- directory: Source
  kind: local
  path: files/hello
variables:
  conf-root: "%{build-root}/Source"
  command-subdir: build

