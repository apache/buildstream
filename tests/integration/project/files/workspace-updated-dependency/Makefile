test.sh: /etc/test/hello.txt
	echo "#!/usr/bin/env sh" > $@
	echo -n "echo '" >> $@
	cat $^ >> $@
	echo -n "'" >> $@
