kind: import
config:
  source: /
  target: /
depends:
- c.bst
sources:
- kind: local
  path: "b"
variables:
  FILE: /file
public:
  bst:
    overlap-whitelist:
    - /file2
    - "%{FILE}3"
