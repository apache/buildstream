kind: manual

depends:
- base.bst

build-depends:
- filename: manual/import-file.bst
  config:
    location: /flying-ponies

config:
  install-commands:
  - cp /flying-ponies/subdir/test.txt %{install-root}
