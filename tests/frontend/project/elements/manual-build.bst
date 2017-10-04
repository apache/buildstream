kind: manual

depends:
  - filename: import-bin.bst
    type: build

config:
  build-commands:
    - echo 'Hi :)'

environment:
  MAKEFLAGS: -j1
