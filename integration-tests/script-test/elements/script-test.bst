kind: script
description: Script test

depends:
  - filename: dependencies/base-platform.bst
    type: build

config:
  commands:
    - "mkdir -p /buildstream/install"
    - "echo 'Hi' > /buildstream/install/test"
