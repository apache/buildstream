kind: script

build-depends:
- base.bst
- base-fail.bst
- base-success.bst

config:
  commands:
  - test -e /foo
