# This element must fail to build

kind: manual

sources:
- kind: local
  path: files/import-source

depends:
- base.bst

config:
  build-commands:
  - false
