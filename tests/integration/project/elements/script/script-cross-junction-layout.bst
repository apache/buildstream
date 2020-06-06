kind: script
description: Write to root using a script element

variables:
  install-root: /buildstream/nstall
  build-root: /buildstream/uild

build-depends:
  - subproject.bst:base.bst
  - subproject.bst:script/script.bst

config:
  layout:
    - element: subproject.bst:base.bst
      destination: /

    - element: subproject.bst:script/script.bst
      destination: /buildstream/uild

  commands:
    - "cp %{build-root}/subtest %{install-root}"
