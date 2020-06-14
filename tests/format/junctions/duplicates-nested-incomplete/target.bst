kind: stack

depends:
- subproject3.bst:target.bst
- subproject.bst:subproject1.bst:target.bst
- subproject.bst:subproject2.bst:target.bst
