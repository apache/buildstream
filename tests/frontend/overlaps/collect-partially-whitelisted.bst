kind: compose

depends:
- filename: a.bst
  type: build
- filename: b-whitelisted.bst
  type: build
- filename: c.bst
  type: build
