kind: manual
description: tar test

depends:
- filename: dependencies/base-platform.bst
  type: build
- filename: dependencies/base-sdk.bst
  type: build

sources:
- kind: tar
  url: file:///home/tristanmaat/Documents/Projects/buildstream/buildstream-tests/tar-test/src.tar.gz

  ref: 164ab309db28e97e96896eb830a04dc3558444fb870ab3930694b5b160327d88
config:
  install-commands:
  - mkdir -p %{install-root}
  - ./test
