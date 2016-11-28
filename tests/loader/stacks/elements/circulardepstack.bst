kind: stack
description: This is a stack with an internal circular dependency
embeds:
- name: horse
  kind: horsy
  depends:
  - rider
- name: pony
  kind: pony
  depends:
  - horse
- name: rider
  kind: rider
  depends:
  - pony
