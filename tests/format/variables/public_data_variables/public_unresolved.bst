kind: import

sources:
  - kind: local
    path: public_unresolved.bst

public:
  integration-commands:
    - echo %{non-existent}
