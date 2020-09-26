kind: configsupported

# Here we test specification of multiple files with the same configuration
#
depends:
- filename:
  - dep.bst
  - dep2.bst
  config:
    enabled: true
