kind: autotools
description: Some kinda autotools element
config:
  configure-commands:
  - pony
depends:
- filename: build-build.bst
  type: build
- filename: run-build.bst
  type: runtime
