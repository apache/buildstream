# Sample makefile for hello.c
#
.PHONY: all install

all: hello

install:
	install -d ${DESTDIR}${PREFIX}/bin
	install -d ${DESTDIR}${PREFIX}/share/doc
	install -m 755 hello ${DESTDIR}${PREFIX}/bin
	install -m 644 hello.txt ${DESTDIR}${PREFIX}/share/doc

hello: hello.c
	$(CC) $< -o $@ -Wall -lhello
