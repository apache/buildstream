kind: manual
description: Workspace mount test

depends:
  - filename: base.bst

sources:
  - kind: local
    path: files/workspace-mount-src/

config:
  build-commands:
    - cc -c hello.c
    - exit 1
