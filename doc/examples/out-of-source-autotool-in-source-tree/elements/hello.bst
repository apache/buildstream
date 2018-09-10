depends:
- base.bst
description: |2

  Hello world example from automake
kind: autotools
sources:
- directory: SourB
  kind: tar
  ref: 80da43bb5665596ee389e6d8b64b4f122ea4b92a685b1dbd813cd1f0e0c2d83f
  url: gnu:automake-1.16.tar.gz
variables:
  conf-root: "%{build-root}/SourB/doc/amhello"
  command-subdir: build

