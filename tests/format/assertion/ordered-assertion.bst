kind: manual
variables:
  thepony: "not pony"
  (?):
  - pony == True:
      thepony: "It's a ponay !"
      (!): It's not pony time yet
  - horsy == True:
      thepony: "It's a horsay !"
      (!): It's not horsy time yet
