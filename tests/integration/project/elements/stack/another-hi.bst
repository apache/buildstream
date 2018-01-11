kind: script
description: Another hi test

depends:
  - filename: base.bst
    type: build

config:
  commands:
    - "mkdir -p /buildstream/install"
    - "echo 'Another hi' > /buildstream/install/another-hi"
