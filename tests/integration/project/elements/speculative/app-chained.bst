kind: autotools
description: |
  Multi-file application for testing ACTION overlay chaining.

  Same as app.bst but also depends on slow-dep.bst. The slow
  dependency keeps this element not-buildable for long enough that
  fire-and-forget compile actions complete and their results appear
  in the action cache. This allows subsequent priming passes to
  resolve ACTION overlays on the link step.

build-depends:
- filename: base/base-debian.bst
  config:
    digest-environment: RECC_REMOTE_PLATFORM_chrootRootDigest
- recc/recc.bst
- speculative/dep.bst
- speculative/slow-dep.bst

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
