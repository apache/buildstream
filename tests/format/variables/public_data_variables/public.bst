kind: import

sources:
  - kind: local
    path: public.bst

public:
  integration-commands:
    - echo %{expand-me}

  test: "%{expand-me}"
