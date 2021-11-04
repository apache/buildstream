kind: manual

depends:
- base.bst

config:
  create-dev-shm: true

  build-commands:
  - |
    mountpoint -q /dev/shm
