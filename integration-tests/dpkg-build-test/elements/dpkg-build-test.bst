kind: dpkg_build
description: dpkg-build test

depends:
- filename: dependencies/base-configure.bst
  type: build

sources:
- kind: local
  path: src
