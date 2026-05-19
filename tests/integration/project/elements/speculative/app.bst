kind: autotools
description: |
  Multi-file application for speculative actions priming test.

  Compiles main.c (includes dep.h from dep element) and util.c
  (only includes local common.h) through recc. This produces 3
  subactions: compile main.c, compile util.c, link.

  When dep.bst changes:
  - main.c compile action needs instantiation (dep.h digest changed)
  - util.c compile action stays stable (no dep files in input tree)
  - link action needs instantiation (main.o changed)

  So priming should produce 2 cache hits (main.c + link adapted) and
  1 direct cache hit (util.c unchanged).

build-depends:
- filename: base/base-debian.bst
  config:
    digest-environment: RECC_REMOTE_PLATFORM_chrootRootDigest
- recc/recc.bst
- speculative/dep.bst

sources:
- kind: tar
  url: project_dir:/files/speculative/multifile.tar.gz
  ref: 1242f38c2b92574bf851fcf51c83a50087debb953aa302763b4e72339a345ab5

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
