all: random copy

random:
	dd if=/dev/urandom count=8 | sha256sum > random

copy: source
	cp source copy
