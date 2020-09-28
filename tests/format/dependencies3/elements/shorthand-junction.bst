kind: configsupported

# Here we test specification of multiple files through the same junction
#
depends:
- filename:
  - target-a.bst
  - target-b.bst
  junction: subproject.bst
  config:
    enabled: true
