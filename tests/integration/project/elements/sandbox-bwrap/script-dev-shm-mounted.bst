kind: script

build-depends:
- base.bst

config:
  create-dev-shm: true

  commands:
  - |
    mountpoint -q /dev/shm
