# This tests that sandbox build-uid / build-gid
# contributions to the cache key do not regress.
#
kind: manual
sources:
- kind: local
  path: files/local

config:
  build-commands:
  - make

sandbox:
  build-uid: 20
  build-gid: 20
