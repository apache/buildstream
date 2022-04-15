#
# This cache key test attempts to make use of all of the variables
# in the default project configuration to ensure their stability.
#
kind: manual
sources:
- kind: local
  path: files/local

config:
  build-commands:
  - echo "%{prefix}"
  - echo "%{exec_prefix}"
  - echo "%{bindir}"
  - echo "%{sbindir}"
  - echo "%{libexecdir}"
  - echo "%{datadir}"
  - echo "%{sysconfdir}"
  - echo "%{sharedstatedir}"
  - echo "%{localstatedir}"
  - echo "%{lib}"
  - echo "%{libdir}"
  - echo "%{debugdir}"
  - echo "%{includedir}"
  - echo "%{docdir}"
  - echo "%{infodir}"
  - echo "%{mandir}"
  - echo "%{build-root}"
  - echo "%{conf-root}"
  - echo "%{install-root}"
  - echo "%{strip-binaries}"
