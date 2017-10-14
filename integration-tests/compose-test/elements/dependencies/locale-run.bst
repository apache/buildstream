kind: script
description: Run autotools-built binary

depends:
  - filename: dependencies/base-platform.bst
    type: build

config:
  commands:
    - "mkdir -p /buildstream/install%{datadir}/locale"
    - "echo 'You should never see this file!' > /buildstream/install%{datadir}/locale/broken"
