kind: script
description: Write to root using a script element

depends:
  - filename: dependencies/base-platform.bst
    type: build

config:
  commands:
    - "mkdir -p /buildstream/install"
    - "echo 'I can not write to root' > /test"
    - "cp /test /buildstream/install"
