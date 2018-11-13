kind: compose

depends:
- filename: compose-symlinks/foo-dir.bst
  type: build
- filename: compose-symlinks/a-foo-symlink.bst
  type: build
- filename: compose-symlinks/integration-move-dir.bst
  type: build

config:
  include-orphans: true
  exclude:
    - dummy
