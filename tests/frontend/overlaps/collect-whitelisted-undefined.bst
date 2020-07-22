kind: compose

depends:
- filename: a-whitelisted.bst
  type: build
- filename: whitelist-undefined.bst
  type: build
- filename: c.bst
  type: build
