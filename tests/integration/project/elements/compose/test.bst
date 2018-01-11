kind: script

depends:
  - filename: base.bst
    type: build

config:
  commands:
    - "mkdir -p %{install-root}/tests"
    - "echo 'This is a test' > %{install-root}/tests/test"
