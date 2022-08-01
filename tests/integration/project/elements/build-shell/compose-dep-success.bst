kind: manual

depends:
- base.bst

config:
  build-commands:
  - "echo 'Hello world'"

public:
  bst:
    integration-commands:
    - echo "Hi" > /integration-success
