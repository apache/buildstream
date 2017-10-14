kind: script
description: Run autotools-built binary

depends:
  - filename: dependencies/base-platform.bst
    type: build

config:
  commands:
    - "mkdir -p /buildstream/install%{includedir}"
    - "echo 'You should never see this file!' > /buildstream/install%{includedir}/broken"
