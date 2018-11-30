kind: import
sources:
- kind: local
  path: files/foo
depends:
- filename: lib2.bst
  junction: junction-B-diff-name.bst
- filename: lib.bst
  junction: junction-A.bst
