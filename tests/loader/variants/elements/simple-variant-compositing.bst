kind: pony
description: Simple test of variant compositing, without fancy dependencies
config:
  somedata: 5
variants:
- variant: pink
  config:
    pony-color: pink
- variant: blue
  config:
    pony-color: blue
    somedata: 6
