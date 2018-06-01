kind: manual
description: A dummy project to utilize a base with existing /tmp folder.

depends:
  - filename: base.bst
    type: build

  - filename: sandbox-bwrap/base-with-tmp.bst

config:
  build-commands:
  - |
    true
