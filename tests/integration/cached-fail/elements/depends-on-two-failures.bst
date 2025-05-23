kind: script

build-depends:
- base-fail.bst
- base-also-fail.bst

config:
  commands:
  - test -e /foo
