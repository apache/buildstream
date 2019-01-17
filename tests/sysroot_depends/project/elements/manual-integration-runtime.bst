kind: manual

depends:
- base.bst

config:
  sysroots:
  - path: /sysroot
    depends:
    - integration.bst

  install-commands:
    - mkdir -p "%{install-root}"
    - echo dummy >"%{install-root}/dummy.txt"
