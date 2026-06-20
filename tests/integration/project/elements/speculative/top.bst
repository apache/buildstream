kind: manual
description: |
  Top element in the speculative actions dependency chain.
  Depends on middle → base. Verifies the full chain builds.

build-depends:
- base/base-debian.bst
- speculative/middle.bst

sources:
- kind: local
  path: files/speculative

config:
  build-commands:
  - |
    test -f /usr/bin/hello && echo "base dependency available"
    test -f /usr/share/speculative/middle.txt && echo "middle dependency available"
  install-commands:
  - |
    mkdir -p %{install-root}/usr/share/speculative
    cp top.txt %{install-root}/usr/share/speculative/top.txt
    cp /usr/share/speculative/middle.txt %{install-root}/usr/share/speculative/from-middle.txt
