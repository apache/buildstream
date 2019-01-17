kind: manual

build-depends:
- base.bst
- a.bst

variables:
  install-root: '/'

config:
  sysroots:
  - path: /sysroot
    build-depends:
    - b.bst
