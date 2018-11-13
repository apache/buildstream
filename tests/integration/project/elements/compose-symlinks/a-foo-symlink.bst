kind: script

depends:
- filename: base.bst
  type: build

config:
  commands:
  - |
    mkdir -p "%{install-root}/bar"
    ln -s "/bar" "%{install-root}/foo"
