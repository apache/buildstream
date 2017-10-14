kind: pip
description: Pip test

variables:
  pip: pip3

depends:
- filename: dependencies/base-platform.bst
  type: build
- filename: dependencies/base-sdk.bst
  type: build

sources:
- kind: tar
  url: file:///hello.tar.xz
  ref: ad96570b552498807abec33c06210bf68378d854ced6753b77916c5ed517610d
