kind: manual
description: Manual test

depends:
  - filename: dependencies/base-platform.bst
    type: build

config:
  configure-commands:
    - "echo './configure' >> test"

  build-commands:
    - "echo 'make' >> test"

  install-commands:
    - "echo 'make install' >> test"
    - "cp test %{install-root}"

  strip-commands:
    - "echo 'strip' >> %{install-root}/test"
