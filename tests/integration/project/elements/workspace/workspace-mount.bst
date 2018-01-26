kind: manual
description: Workspace mount test

depends:
  - filename: base.bst
    type: build

sources:
  - kind: local
    path: files/workspace-mount-src/

config:
  build-commands:
    - g++ -c hello.cpp
