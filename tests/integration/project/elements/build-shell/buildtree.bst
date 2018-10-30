kind: manual
description: |
  Puts a file in the build tree so that build tree caching and staging can be tested.

depends:
  - filename: base.bst
    type: build

config:
  build-commands:
    - "echo 'Hi' > %{build-root}/test"
