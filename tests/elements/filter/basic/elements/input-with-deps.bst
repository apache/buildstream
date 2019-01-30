kind: import

depends:
- filename: input.bst

sources:
- kind: local
  path: files

public:
  bst:
    split-rules:
      baz:
      - /baz
