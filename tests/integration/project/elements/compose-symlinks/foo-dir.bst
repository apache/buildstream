kind: script

depends:
- filename: base.bst
  type: build

config:
  commands:
  - |
    mkdir -p "%{install-root}/foo"
    echo test >"%{install-root}/foo/foo.txt"
