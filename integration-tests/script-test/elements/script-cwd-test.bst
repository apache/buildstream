kind: script
description: Write to root using a script element

variables:
  cwd: /buildstream

depends:
  - filename: dependencies/base-platform.bst
    type: build

config:
  commands:
    - "echo 'test' > test"
    - "cp /buildstream/test %{install-root}"
