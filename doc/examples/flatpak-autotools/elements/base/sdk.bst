kind: import
description: Import the base freedesktop SDK
sources:
- kind: ostree
  url: flathub:repo/
  gpg-key: keys/flathub.gpg
  (?):
  - arch == "x86-64":
      track: runtime/org.freedesktop.BaseSdk/x86_64/1.6
      ref: 7306169ea9c563f3ce75bb57be9e94b0acf1d742edacab0aa751cf6646a4b52e
  - arch == "x86-32":
      track: runtime/org.freedesktop.BaseSdk/i386/1.6
      ref: 63f9537eea89448ec865f907a3ec89b261493b3d999121a81603c827b6219d20
config:
  source: files
  target: usr
