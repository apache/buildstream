kind: script
depends:
  - filename: base.bst
    type: build
config:
  commands:
    - "mkdir -p /buildstream/install"
    - "echo 'Hi' > /buildstream/install/hi"
