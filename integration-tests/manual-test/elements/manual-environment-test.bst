kind: manual
description: Manual test

variables:
  max-jobs: 2

depends:
  - filename: dependencies/base-platform.bst
    type: build

config:
  install-commands:
    - "echo $MAKEFLAGS >> test"
    - "echo $V >> test"
    - "cp test %{install-root}"

environment:
  MAKEFLAGS: -j%{max-jobs} -Wall
  V: 2

# FIXME: Test environment-nocache
