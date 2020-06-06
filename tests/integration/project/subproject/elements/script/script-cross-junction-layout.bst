kind: script
description: Write to root using a script element

variables:
  install-root: /buildstream/nstall
  build-root: /buildstream/uild

build-depends:
  - subsubproject.bst:base.bst
  - subsubproject.bst:script/script.bst

config:
  layout:
    - element: subsubproject.bst:base.bst
      destination: /

    - element: subsubproject.bst:script/script.bst
      destination: /buildstream/uild

  commands:
    - "cp %{build-root}/subsubtest %{install-root}"
