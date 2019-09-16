kind: import
sources:
- kind: local
  path: files
public:
  bst:
    split-rules:
      foo:
      - /foo
      bar:
      - /bar
    integration-commands:
    - foo
    - bar
