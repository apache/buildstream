# This tests that staging into an alternative
# prefix affects the cache key
#
kind: manual
sources:
- kind: local
  path: files/local

depends:
- elements/build1.bst
- filename: elements/build1.bst
  config:
    location: /opt
