kind: script

depends:
- filename: script/no-tmpdir.bst
  type: build

config:
  commands:
  - |
    mkdir -p /tmp/blah
