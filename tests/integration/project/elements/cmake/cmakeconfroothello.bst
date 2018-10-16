kind: cmake
description: Cmake test

depends:
  - base.bst

sources:
  - kind: tar
    directory: Source
    url: project_dir:/files/cmakehello.tar.gz
    ref: 508266f40dbc5875293bd24c4e50a9eb6b88cbacab742033f7b92f8c087b64e5

variables:
  conf-root: "%{build-root}/Source"
  command-subdir: build
