kind: manual

depends:
- base.bst

config:
  create-dev-shm: false

  build-commands:
  - |
    ! mountpoint -q /dev/shm
