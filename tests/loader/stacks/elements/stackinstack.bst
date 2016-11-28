kind: stack
description: This is a stack embedded in a stack
embeds:
- name: horse
  kind: stack
  embeds:
  - name: impossible
    kind: mission
    description: You cannot embed stacks inside stacks
