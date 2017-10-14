kind: manual
description: bzr test

depends:
- filename: dependencies/base-platform.bst
  type: build
- filename: dependencies/base-sdk.bst
  type: build

sources:
- kind: ostree
  url: file:///home/tristanmaat/Documents/Projects/buildstream/buildstream-tests/ostree-test/src
  directory: somewhere
  track: test
  ref: bd5cc009f076d4fb696447bb671512e71897eacc2fc198c98d3af69fcdf59f11

config:
  install-commands:
  - mkdir -p %{install-root}
  - somewhere/test
