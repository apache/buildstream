kind: manual
description: Workspace mount test

depends:
  - filename: base.bst
    type: build

sources:
  - kind: local
    path: files/workspace-mount-src/

variables:
  command-subdir: build

config:
  build-commands:
    - cc -c ../hello.c
