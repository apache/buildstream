kind: stack

depends:
- subproject.bst:subtarget.bst
- subsubproject-again.bst:target.bst
- subsubproject-conflict.bst:target.bst
