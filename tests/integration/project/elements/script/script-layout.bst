kind: script
description: Write to root using a script element

variables:
  install-root: /buildstream/nstall
  build-root: /buildstream/uild

build-depends:
  - base.bst
  - filename: script/script.bst
    config:
      location: /buildstream/uild

config:
  commands:
  - "cp %{build-root}/test %{install-root}"
