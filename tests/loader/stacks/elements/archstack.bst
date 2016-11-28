kind: stack
description: This is a stack, and it's elements include stuff
embeds:
- name: rider
  kind: rider
arches:
  x86_64:
    embeds:
    - name: pony
      kind: pony
  x86_32:
    embeds:
    - name: horse
      kind: horsy
  