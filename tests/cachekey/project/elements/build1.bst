# The cache key calculation algorithm is the same
# for all build elements, better to only have one test
# for it and without too much noise from changes which
# would cause is to change the test case.
#
# Lets stick with manual, the most basic build element.
kind: manual
sources:
- kind: local
  path: files/local

config:
  build-commands:
  - make
