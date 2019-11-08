kind: manual

depends:
- base.bst 

config:
  build-commands:
  - cc test_shm.c

  install-commands:
  - ./a.out

sources:
- kind: local
  path: files/test_shm.c
