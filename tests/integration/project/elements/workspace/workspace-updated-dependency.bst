kind: manual

depends:
  - base.bst
  - workspace/dependency.bst

sources:
  - kind: local
    path: files/workspace-updated-dependency/

config:
  build-commands:
    - make
    - chmod +x test.sh
    - mkdir -p %{install-root}/usr/bin/
    - cp test.sh %{install-root}/usr/bin/
    - ls %{install-root}
