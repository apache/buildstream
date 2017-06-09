kind: pony
description: |
  An element with host-arches and arches conditionals.

  The 'arches' conditional follows --target-arch if specified, while the
  'host-arches' conditional does not. The 'arches' conditional overrides
  'host-arches' if both for some reason try to override the same thing.
config:
  number: 5
arches:
  x86_64:
    config:
      number: 6
host-arches:
  x86_64:
    config:
      number: 66
  armv8:
    config:
      number: 88
