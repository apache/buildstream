# Sample makefile for hello.c
#
.PHONY: all install

all: hello

install:
	install -d ${DESTDIR}${PREFIX}/bin
	install -m 755 hello ${DESTDIR}${PREFIX}/bin

hello: hello.c
	$(CC) -DGREETING_MESSAGE="\"${GREETING}\"" -Wall -o $@ $<
