kind: stack
description: This is a stack, and variants define what other elements to embed
embeds:
- name: rider
  kind: rider
variants:
- variant: pony
  embeds:
  - name: pony
    kind: pony
- variant: horse
  embeds:
  - name: horse
    kind: horsy
