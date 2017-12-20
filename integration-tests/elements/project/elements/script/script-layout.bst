kind: script
description: Write to root using a script element

variables:
  install-root: /buildstream/nstall
  build-root: /buildstream/uild

depends:
  - filename: base.bst
    type: build
  - filename: script/script.bst
    type: build

config:
  layout:
    - element: base.bst
      destination: /

    - element: script/script.bst
      destination: /buildstream/uild

  commands:
    - "cp %{build-root}/test %{install-root}"
