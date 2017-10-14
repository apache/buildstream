kind: script
description: Cmake binary run test

depends:
  - filename: dependencies/base-platform.bst
    type: build
  - filename: step7.bst
    type: build

config:
  commands:
    - "/usr/bin/Tutorial 9 > /buildstream/install/test"
