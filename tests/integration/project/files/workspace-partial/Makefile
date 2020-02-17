all: copy1 copy2

random:
	dd if=/dev/urandom count=8 | sha256sum > random

copy1: source1
	cp source1 copy1

copy2: source2
	cp source2 copy2
