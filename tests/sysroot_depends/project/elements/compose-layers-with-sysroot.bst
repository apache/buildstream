kind: manual

build-depends:
- base.bst

variables:
  install-root: "/"

config:
  sysroots:
  - path: /other-sysroot
    build-depends:
    - layer2.bst
