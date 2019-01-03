kind: manual
variables:
  command-subdir: bin-files
config:
  install-commands:
  - "cp %{build-root}/usr/bin/hello %{install-root}"
sources:
- kind: local
  path: files
