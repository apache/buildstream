kind: compose

depends:
  - filename: dependencies/amhello.bst
    type: build

config:
  include:
    - runtime
