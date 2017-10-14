kind: script
description: Write to root using a script element

variables:
  install-root: /buildstream/nstall
  build-root: /buildstream/uild

depends:
  - filename: dependencies/base-platform.bst
    type: build
  - filename: script-test.bst
    type: build

config:
  layout:
    - element: dependencies/base-platform.bst
      destination: /

    - element: script-test.bst
      destination: "%{build-root}"

  commands:
    - "cp %{build-root}/test %{install-root}"
