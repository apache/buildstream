kind: autotools
description: recc test with autotools

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
    action-cache-enable-update: true

environment:
  CC: recc gcc
  RECC_LOG_LEVEL: debug
  RECC_LOG_DIRECTORY: .recc-log
  RECC_DEPS_GLOBAL_PATHS: 1
  RECC_NO_PATH_REWRITE: 1
  RECC_LINK: 1
  RECC_CACHE_ONLY: 1
  RECC_CACHE_UPLOAD_LOCAL_BUILD: 1
  RECC_SERVER: unix:/tmp/casd.sock
