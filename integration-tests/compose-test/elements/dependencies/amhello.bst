kind: autotools
description: Autotools test

depends:
- filename: dependencies/base-platform.bst
  type: build
- filename: dependencies/base-sdk.bst
  type: build

sources:
- kind: tar
  url: file:///home/phillipsmyth/projects/buildstream/integration-tests/compose-test/src/amhello.tar.gz
  ref: 3aa3c2bf7a488fea24303c4d98d1b5c0a72734f61615b935cf62e4e126b127d2
