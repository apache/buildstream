kind: compose

depends:
- filename: c.bst
  type: build
- filename: a-sub.bst
  junction: sub-project.bst
  type: build
- filename: z-sub.bst
  junction: sub-project.bst
  type: build
