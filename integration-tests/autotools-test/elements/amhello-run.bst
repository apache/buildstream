kind: script
description: Run autotools-built binary

depends:
  - filename: dependencies/base-platform.bst
    type: build
  - filename: amhello.bst
    type: build

config:
  commands:
    - "/usr/bin/hello > /buildstream/install/test"
