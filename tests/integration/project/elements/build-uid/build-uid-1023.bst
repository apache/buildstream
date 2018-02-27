kind: manual

depends:
  - filename: base.bst
    type: build

config:
  build-commands:
    - "[ `id -u` = 1023 -a `id -g` = 3490 ]"
