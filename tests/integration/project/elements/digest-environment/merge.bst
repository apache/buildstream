kind: manual

depends:
  - filename: base.bst
    type: build
    config:
      digest-environment: MERGED_DIGEST
  - filename: manual/import-file.bst
    type: build
    config:
      digest-environment: MERGED_DIGEST

config:
  build-commands:
    - env
    - test "$MERGED_DIGEST" = "469369597f4faa56c4b8338d6a948c8c1d4f29e6ea8f4d4d261cac4182bcef48/1389"
