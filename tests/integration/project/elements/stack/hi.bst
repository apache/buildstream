kind: script
depends:
  - filename: base.bst
    type: build
config:
  commands:
    - "mkdir -p %{install-root}"
    - "echo 'Hi' > %{install-root}/hi"
