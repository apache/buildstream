kind: script

build-depends:
- script/no-tmpdir.bst

config:
  commands:
  - |
    mkdir -p /tmp/blah
