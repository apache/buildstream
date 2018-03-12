all: test.sh

hello: /etc/test/hello.txt
	cp $^ $@

tests: /etc/test/tests/*.txt
	cp $^ $@

test.sh: hello tests
	echo "#!/usr/bin/env sh" > $@
	echo -n "echo '" >> $@
	cat $^ >> $@
	echo -n "'" >> $@
