kind: manual
description: Test element without runtime dependencies

build-depends:
- autotools/amhello.bst

config:
  install-commands:
  - echo Test > %{install-root}/test
