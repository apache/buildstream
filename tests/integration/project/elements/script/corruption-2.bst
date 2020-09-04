kind: script

build-depends:
- base.bst
- script/corruption-image.bst

config:
  commands:
  - echo smashed >>/canary
