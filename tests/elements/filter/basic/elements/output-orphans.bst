kind: filter
depends:
- filename: input.bst
  type: build
config:
  exclude:
  - foo
  - bar
  include-orphans: True
