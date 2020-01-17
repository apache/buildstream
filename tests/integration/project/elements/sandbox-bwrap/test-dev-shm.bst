kind: manual

depends:
- base.bst

config:
  build-comamnds:
  - cc test_shm.c

  install-commands:
  - ./a.out

sources:
- kind: local
  path: files/test_shm.c
