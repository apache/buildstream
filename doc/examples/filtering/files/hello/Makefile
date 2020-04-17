# Sample makefile for hello.c
#
.PHONY: all install

all: hello

install:
	install -d ${DESTDIR}${PREFIX}/bin
	install -m 755 hello ${DESTDIR}${PREFIX}/bin

hello: hello.c
	extra_flags="";                                               \
	if [ -f "${PREFIX}/share/libhello/default-person.txt" ]; then \
	  extra_flags=-DDEFAULT_PERSON="\"$$(cat ${PREFIX}/share/libhello/default-person.txt)\""; \
	fi;                                                           \
	$(CC) $< -o $@ $${extra_flags} -Wall -lhello
