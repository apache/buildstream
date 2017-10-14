kind: script
description: Write to root using a script element

depends:
  - filename: dependencies/base-platform.bst
    type: build

config:
  root-read-only: False

  commands:
    - "mkdir -p /buildstream/install"
    - "echo 'I can write to root' > /test"
    - "cp /test /buildstream/install"
