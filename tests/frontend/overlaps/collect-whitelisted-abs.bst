kind: compose

depends:
- filename: a-whitelisted-abs.bst
  type: build
- filename: b-whitelisted-abs.bst
  type: build
- filename: c.bst
  type: build
