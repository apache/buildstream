kind: manual

depends:
  - filename: base.bst
    type: build
    config:
      digest-environment: BASE_DIGEST
  - filename: manual/import-file.bst
    type: build
    config:
      digest-environment: IMPORT_DIGEST

config:
  build-commands:
    - env
    - test "$BASE_DIGEST" = "63450d93eab71f525d08378fe50960aff92b0ec8f1b0be72b2ac4b8259d09833/1227"
    - test "$IMPORT_DIGEST" = "eec5ed9053acb296a8e7a30ab7ee173abf4f7392b8228ba7644cd5b51a5cfdeb/162"
