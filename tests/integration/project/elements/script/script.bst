kind: script
description: Script test

build-depends:
- base.bst

config:
  commands:
    - "echo 'Hi' > %{install-root}/test"
