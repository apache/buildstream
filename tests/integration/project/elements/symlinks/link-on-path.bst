kind: manual

depends:
- filename: base.bst
  type: build

config:
  install-commands:
    - |
      cd "%{install-root}"
      cp -r /bin /lib .
      mv bin altbin
      ln -s altbin bin
