kind: script
description: Run pip-built binary

depends:
- filename: dependencies/base-platform.bst
  type: build
- filename: dependencies/base-sdk.bst
  type: build
- filename: hello.bst
  type: build

config:
  commands:
    - "/usr/bin/hello > /buildstream/install/test"
