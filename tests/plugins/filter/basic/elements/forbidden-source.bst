kind: filter
depends:
- filename: output-include.bst
  type: build
config:
  include:
  - foo
sources:
- kind: local
  path: files
