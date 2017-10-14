kind: manual
description: bzr test

depends:
- filename: dependencies/base-platform.bst
  type: build
- filename: dependencies/base-sdk.bst
  type: build

sources:
- kind: bzr
  url: file:///src
  track: trunk

  ref: '2'
config:
  install-commands:
    - "mkdir -p %{install-root}"
    - "./test"
