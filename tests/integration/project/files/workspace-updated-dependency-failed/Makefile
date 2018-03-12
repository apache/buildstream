all: test.sh

hello: /etc/test/hello.txt
	cp $^ $@

brazil: /etc/test/brazil.txt
	cp $^ $@

test.sh: hello brazil
	echo "#!/usr/bin/env sh" > $@
	echo -n "echo '" >> $@
	cat $^ >> $@
	echo -n "'" >> $@
