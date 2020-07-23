kind: manual

variables:
  hello: "Hello mister %{pony}"
  greeting: "The %{hello} string twice: %{hello} again"
  pony: "The pony is %{undefined}"

config:
  build-commands:
  - Some indirectly undefined variable %{greeting}
