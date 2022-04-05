kind: manual
variables:
  result: "a pony"
  (?):
  - farm == [ "zebry" ]:
      result: "a zebry"
  - farm == [ "horsy", "pony" ]:
      result: "a pony and a horsy"
  - farm == [ "horsy", "pony", "zebry" ]:
      result: "all the animals"
