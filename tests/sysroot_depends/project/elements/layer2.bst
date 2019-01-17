kind: manual

depends:
- layer2-files.bst

build-depends:
- base.bst

config:
  sysroots:
  - path: /sysroot
    depends:
    - layer1.bst

  install-commands:
  - mkdir -p "%{install-root}"
  - |
    for file in /*; do
      if test -f "${file}"; then
        cp "${file}" "%{install-root}"
      fi
    done
