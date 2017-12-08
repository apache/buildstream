kind: compose

depends:
- filename: a-whitelisted.bst
  type: build
- filename: b-whitelisted.bst
  type: build
- filename: c.bst
  type: build
