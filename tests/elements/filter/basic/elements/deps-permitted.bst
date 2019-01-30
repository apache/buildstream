kind: filter
depends:
- filename: input.bst
  type: build
- filename: output-exclude.bst
  type: runtime
- filename: output-orphans.bst
  type: runtime
config:
  include:
  - foo
