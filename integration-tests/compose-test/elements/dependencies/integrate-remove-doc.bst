kind: stack
description: remove the docs with an integration command

depends:
- dependencies/amhello-full.bst

public:
  bst:
    integration-commands:
    - rm -rf /usr/share/doc/amhello
