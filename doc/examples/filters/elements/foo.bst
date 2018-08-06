kind: local 

config:
  source:
  - kind: local
    path: files/foo/
    
public:
  bst:
    split-rules:
      bar:
        - "foo/bar/*"
      baz:
        - "foo/baz/*"
      
