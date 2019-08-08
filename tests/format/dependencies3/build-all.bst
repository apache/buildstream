kind: import

sources:
- kind: local
  path: all-all.bst

depends:
- filename: dep.bst
  type: build
- filename: dep.bst
  type: all
