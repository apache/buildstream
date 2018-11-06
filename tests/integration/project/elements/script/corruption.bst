kind: script

depends:
- filename: base.bst
  type: build
- filename: script/corruption-image.bst
  type: build
- filename: script/corruption-integration.bst
  type: build

variables:
  install-root: "/"

config:
  layout:
  - element: base.bst
    destination: "/"
  - element: script/corruption-image.bst
    destination: "/"
  - element: script/corruption-integration.bst
    destination: "/"
