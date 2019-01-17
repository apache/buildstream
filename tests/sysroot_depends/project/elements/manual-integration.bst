kind: manual

build-depends:
- base.bst

config:
  sysroots:
  - path: /sysroot
    build-depends:
    - integration.bst

  install-commands:
  - mkdir -p "%{install-root}/sysroot"
  - if test -f /sysroot/integrated.txt; then cp /sysroot/integrated.txt "%{install-root}/sysroot"; fi
  - if test -f /integrated.txt; then cp /integrated.txt "%{install-root}"; fi
