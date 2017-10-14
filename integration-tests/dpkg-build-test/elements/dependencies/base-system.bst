kind: manual
depends:
- filename: dependencies/base-platform.bst
  type: build
sources:
- kind: git
  url: https://gitlab.com/BuildStream/buildstream-sysroots.git
  track: dpkg-build
  ref: ecf14954e4298ce5495f701464339162fad73f30
config:
  install-commands:
  - xz -d dpkg-build-sysroot.tar.xz
  - tar xf dpkg-build-sysroot.tar -C %{install-root} --no-same-owner
