kind: compose

depends:
- filename: compose-symlinks/a-overlay.bst
  type: build
- filename: compose-symlinks/base.bst
  type: build

config:
  include:
  - runtime
