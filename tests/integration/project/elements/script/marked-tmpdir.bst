kind: compose

build-depends:
- base.bst

public:
  bst:
    split-rules:
      remove:
        - "/tmp/**"
        - "/tmp"
