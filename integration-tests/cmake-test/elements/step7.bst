kind: cmake
description: Cmake test

depends:
  - filename: dependencies/base-platform.bst
    type: build
  - filename: dependencies/base-sdk.bst
    type: build

sources:
  - kind: tar
    url: file:///home/tristanmaat/Documents/Projects/buildstream/buildstream-tests/cmake-test/src/step7.tar.gz
    ref: 9591707afbae77751730b4af4c52a18b1cdc4378237bc64055f099bc95c330db
