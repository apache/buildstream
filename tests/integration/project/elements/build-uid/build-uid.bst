kind: manual

depends:
  - filename: base.bst
    type: build

sandbox:
  build-uid: 1024
  build-gid: 1048

config:
  build-commands:
    - "[ `id -u` = 1024 -a `id -g` = 1048 ]"
