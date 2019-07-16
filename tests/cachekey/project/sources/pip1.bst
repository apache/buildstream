kind: import

sources:
- kind: git
  url: https://example.com/foo/foobar.git
  ref: b99955530263172ed1beae52aed7a33885ef781f
- kind: pip
  url: https://pypi.example.com/simple
  packages:
  - horses
  - ponies
  ref: 'horses==0.0.1\nponies==0.0.2'
