kind: import
description: Import the base freedesktop SDK
sources:
- kind: ostree
  url: flathub:repo/
  gpg-key: keys/flathub.gpg
  (?):
  - arch == "x86_64":
      track: runtime/org.freedesktop.Sdk/x86_64/18.08
      ref: 03ebd5e0d55333b3926fba9ad7163a665a5f22f3eb94f6fc0d7cb55af8888c75
  - arch == "i386":
      track: runtime/org.freedesktop.Sdk/i386/18.08
      ref: f7d80db9d0eb219eba0a8d9ed1ae4d09fbda708fb49fd218839cbd4d745b01cd
config:
  source: files
  target: usr
