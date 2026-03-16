kind: manual
description: |
  Middle element in the speculative actions dependency chain.
  Depends on base (which uses recc for subaction recording).

build-depends:
- base/base-debian.bst
- speculative/base.bst

sources:
- kind: local
  path: files/speculative

config:
  build-commands:
  - |
    test -f /usr/bin/hello && echo "base dependency available"
  install-commands:
  - |
    mkdir -p %{install-root}/usr/share/speculative
    cp middle.txt %{install-root}/usr/share/speculative/middle.txt
