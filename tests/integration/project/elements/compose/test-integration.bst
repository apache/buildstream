kind: stack

depends:
- base.bst

public:
  bst:
    integration-commands:
    - "mkdir -p /tests"
    - "echo 'This is a test' > /tests/test"
