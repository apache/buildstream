kind: script

build-depends:
- base.bst

config:
  create-dev-shm: false

  commands:
  - |
    ! mountpoint -q /dev/shm
