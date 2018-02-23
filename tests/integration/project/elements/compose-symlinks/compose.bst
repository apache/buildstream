kind: compose

depends:
- filename: compose-symlinks/base.bst
  type: build
- filename: compose-symlinks/overlay.bst
  type: build

config:
  include:
  - runtime
