kind: configsupported

# Here we test that the same dependency will be supplied to the
# plugin twice if they are listed twice (even though in this simple
# test case, we supply a redundant configuration, in real life it
# can be useful to configure the same dependency differently multiple
# times)
#
depends:
- filename: dep.bst
  config:
    enabled: true
- filename: dep.bst
  config:
    enabled: true
