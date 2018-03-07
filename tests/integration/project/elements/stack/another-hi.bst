kind: script
description: Another hi test

depends:
  - filename: base.bst
    type: build

config:
  commands:
    - "mkdir -p %{install-root}"
    - "echo 'Another hi' > %{install-root}/another-hi"
