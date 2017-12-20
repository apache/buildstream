kind: script
description: Script test

depends:
  - filename: base.bst
    type: build

config:
  commands:
    - "echo 'Hi' > %{install-root}/test"
