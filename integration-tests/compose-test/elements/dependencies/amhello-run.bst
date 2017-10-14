kind: script
description: Run autotools-built binary

depends:
  - filename: dependencies/base-platform.bst
    type: build
  - filename: dependencies/amhello.bst
    type: build

config:
  commands:
    - "mkdir -p /buildstream/install/tests"
    - "/usr/bin/hello > /buildstream/install/tests/test"
    - "echo BLABLABLA %{debugdir} >> /buildstream/install/tests/test"
