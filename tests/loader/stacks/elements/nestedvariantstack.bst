kind: stack
description: This is a stack, and variants define how the embedded elements are configured
embeds:
- name: rider
  kind: rider
  config:
    number: 5
  variants:
  - variant: pony
    config:
      number: 6
  - variant: horse
    config:
      number: 7
- name: pony
  kind: pony
  config:
    number: 5
  variants:
  - variant: pony
    config:
      number: 6
- name: horse
  kind: horsy
  config:
    number: 5
  variants:
  - variant: horse
    config:
      number: 7
variants:
- variant: pony
- variant: horse
