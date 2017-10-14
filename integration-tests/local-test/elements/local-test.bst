kind: manual
description: bzr test

depends:
- filename: dependencies/base-platform.bst
  type: build
- filename: dependencies/base-sdk.bst
  type: build

sources:
- kind: local
  path: src
  directory: somewhere

config:
  install-commands:
  - "mkdir -p %{install-root}"
  - "somewhere/test"
