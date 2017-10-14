kind: manual
description: bzr test

depends:
- filename: dependencies/base-platform.bst
  type: build
- filename: dependencies/base-sdk.bst
  type: build

sources:
- kind: git
  url: file:///home/tristanmaat/Documents/Projects/buildstream/buildstream-tests/git-test/src
  track: master

  ref: 11084171004f9e83f90a3c17615e6a6055435717
config:
  install-commands:
  - mkdir -p %{install-root}
  - ./test
