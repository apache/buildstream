kind: manual

depends:
  - filename: base.bst
    type: build

config:
  build-commands:
    - "[ `id -u` = 0 -a `id -g` = 0 ]"