kind: stack
description: This is a stack whos embedded elements have arch conditionals
embeds:
- name: rider
  kind: rider
  config:
    color: brown
  arches:
    x86_64:
      config:
        color: pink
    x86_32:
      config:
        color: blue
