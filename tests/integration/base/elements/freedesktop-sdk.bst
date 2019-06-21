kind: junction
sources:
- kind: git
  url: https://gitlab.com/freedesktop-sdk/freedesktop-sdk/
  track: freedesktop-sdk-18.08.31.1-bst2
  ref: 5c639b8d553016ea6c28ea160a572da2e189745e
config:
  options:
    target_arch: '%{arch}'
