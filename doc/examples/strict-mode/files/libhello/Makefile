# Sample makefile for hello library
#
.PHONY: all install

all: libhello.so libhello.a

install: all
	install -d ${DESTDIR}${PREFIX}/lib
	install -d ${DESTDIR}${PREFIX}/include
	install -m 644 libhello.so ${DESTDIR}${PREFIX}/lib
	install -m 644 libhello.a ${DESTDIR}${PREFIX}/lib
	install -m 644 libhello.h ${DESTDIR}${PREFIX}/include

%.o: %.c %.h
	$(CC) -c $< -o $@ -Wall

libhello.a: libhello.o
	$(AR) rcs $@ $^

libhello.so: libhello.o
	$(CC) -shared -o $@ $<
