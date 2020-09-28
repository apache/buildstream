kind: configsupported

# Here we test an incorrect type of filename, e.g. a dictionary
#
depends:
- filename:
  - target-a.bst
  - target-b.bst
  - multiple: foo
    components: bar
  junction: subproject.bst
  config:
    enabled: true
