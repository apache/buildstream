kind: compose

depends:
- filename: base.bst
  type: build

public:
  bst:
    split-rules:
      remove:
        - "/tmp/**"
        - "/tmp"
