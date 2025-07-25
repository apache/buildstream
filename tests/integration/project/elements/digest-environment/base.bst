kind: manual

depends:
  - filename: base.bst
    type: build
    config:
      digest-environment: BASE_DIGEST

config:
  build-commands:
    - env
    - test "$BASE_DIGEST" = "63450d93eab71f525d08378fe50960aff92b0ec8f1b0be72b2ac4b8259d09833/1227"
