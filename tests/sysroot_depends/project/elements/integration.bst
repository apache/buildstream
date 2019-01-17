kind: manual

depends:
- base.bst

config:
  install-commands:
    - echo 0 >"%{install-root}/integrated.txt"

public:
  bst:
    integration-commands:
    - echo 1 >/integrated.txt
