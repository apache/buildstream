kind: script

build-depends:
- base.bst
- base-fail.bst

config:
  commands:
  - test -e /foo
