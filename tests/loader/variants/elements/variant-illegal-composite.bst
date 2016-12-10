kind: pony
description: This variant overrides a config value with an incorrect type
config:
  number: 5
variants:
- variant: first
  config:
    number: four
- variant: second
  config:
    number: six
