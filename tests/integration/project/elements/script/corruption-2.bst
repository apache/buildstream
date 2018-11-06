kind: script

depends:
- filename: base.bst
  type: build
- filename: script/corruption-image.bst
  type: build

config:
  commands:
  - echo smashed >>/canary
