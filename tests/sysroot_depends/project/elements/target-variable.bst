kind: manual

build-depends:
- base.bst

variables:
  mydir: test
  install-root: "/path"

config:
  sysroots:
  - path: "/path/%{mydir}"
    build-depends:
    - b.bst
