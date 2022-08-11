kind: manual

depends:
- base.bst

config:
  build-commands:
  - "echo 'Goodbye world'"

public:
  bst:
    integration-commands:
    - exit 1
