kind: manual

depends:
  - filename: base.bst
    type: build

sandbox:
  build-arch: '%{build_arch}'

config:
  build-commands:
    - true
