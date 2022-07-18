kind: junction
sources:
- kind: local
  path: subproject


config:
  options:
    (?):
    - use_species:
        classifier: species
    - not use_species:
        classifier: animal
