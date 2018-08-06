kind: import 

sources:
- kind: local
  path: files/foo/

config: 
  target: /
    
public:
  bst:
    split-rules:
      bar:
        - "bar*"
      baz:
        - "baz*"
      
