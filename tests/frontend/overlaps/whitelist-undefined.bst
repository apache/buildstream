kind: import
config:
  source: /
  target: /
depends:
- b-whitelisted.bst
sources:
- kind: local
  path: "a"
public:
  bst:
    overlap-whitelist:
    - "%{undefined-variable}/*"
