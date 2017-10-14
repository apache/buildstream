kind: dpkg_deploy
description: dpkg-deploy test

depends:
- filename: dependencies/base-configure.bst
  type: build
- filename: dpkg-build-test.bst
  type: build

config:
  base: dependencies/base-configure.bst
  input: dpkg-build-test.bst
