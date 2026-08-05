kind: stack
description: |

  Main stack target for the bst build test

depends:
- import-local-files.bst
- import-remote-files.bst

config:
  build-commands:
    - "cc greeting.c -o greeting"
