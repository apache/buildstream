kind: junction
sources:
- kind: git
  url: https://gitlab.com/freedesktop-sdk/freedesktop-sdk/
  track: '18.08'
  ref: ddde36212f574fbdb66b5cca3d4b411aec22ee82
config:
  options:
    target_arch: '%{arch}'
