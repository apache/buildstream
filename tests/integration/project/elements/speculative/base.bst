kind: autotools
description: |
  Base element using recc for subaction recording.
  Compiles amhello through recc via remote-apis-socket so each
  compiler invocation is recorded as a subaction.

build-depends:
- filename: base/base-debian.bst
  config:
    digest-environment: RECC_REMOTE_PLATFORM_chrootRootDigest
- recc/recc.bst

sources:
- kind: tar
  url: project_dir:/files/amhello.tar.gz
  ref: 534a884bc1974ffc539a9c215e35c4217b6f666a134cd729e786b9c84af99650

sandbox:
  remote-apis-socket:
    path: /tmp/casd.sock

environment:
  CC: recc gcc
  RECC_LOG_LEVEL: debug
  RECC_LOG_DIRECTORY: .recc-log
  RECC_DEPS_GLOBAL_PATHS: 1
  RECC_NO_PATH_REWRITE: 1
  RECC_LINK: 1
  RECC_SERVER: unix:/tmp/casd.sock
