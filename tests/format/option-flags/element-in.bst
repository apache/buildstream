kind: manual
variables:
  result: "a pony"
  (?):
  - ("zebry" in farm):
      result: "a zebry"
  - ("pony" not in farm):
      result: "no pony"
  - (animal not in farm):
      result: "no horsy"
