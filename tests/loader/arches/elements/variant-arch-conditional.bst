kind: pony
description: Test out arch conditionals nested inside variant declarations
config:
  number: 5
variants:
- variant: pink
  config:
    number: 6
  arches:
    x86_64:
      config:
        number: 7
    x86_32:
      config:
        number: 8
- variant: blue
  config:
    number: 4
  arches:
    x86_64:
      config:
        number: 3
    x86_32:
      config:
        number: 2
