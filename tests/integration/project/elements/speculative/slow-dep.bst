kind: manual
description: |
  Slow dependency that takes time to build.
  Used to keep downstream elements not-buildable while fire-and-forget
  priming actions complete, enabling ACTION overlay resolution.

build-depends:
- filename: base/base-debian.bst

sources:
- kind: local
  path: files/speculative/slow-dep-files

config:
  install-commands:
  - |
    sleep 2
    mkdir -p %{install-root}/usr/lib/speculative
    cp slow.txt %{install-root}/usr/lib/speculative/slow.txt
