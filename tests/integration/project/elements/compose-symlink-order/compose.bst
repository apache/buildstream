kind: compose
depends:
- filename: compose-symlink-order/b.bst
  type: build

config:
  exclude:
    - devel
