kind: script

build-depends:
- base.bst

config:
  commands:
  - touch %{install-root}/foo
  - false
