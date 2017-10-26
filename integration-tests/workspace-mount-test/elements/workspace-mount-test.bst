kind: manual
description: workspace mount test

depends:
- filename: dependencies/base-platform.bst
  type: build
- filename: dependencies/base-sdk.bst
  type: build

sources:
- kind: local
  path: src

config:
  build-commands:
  - g++ -c hello.cpp
