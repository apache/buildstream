kind: manual
variables:
  command-subdir: dev-files
config:
  install-commands:
  - "cp %{build-root}/usr/include/pony.h %{install-root}"
sources:
- kind: local
  path: files
