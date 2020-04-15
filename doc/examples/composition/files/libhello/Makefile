# Sample makefile for hello library
#
.PHONY: all install

all: libhello.so

install:
	install -d ${DESTDIR}${PREFIX}/lib
	install -d ${DESTDIR}${PREFIX}/include
	install -m 644 libhello.so ${DESTDIR}${PREFIX}/lib
	install -m 644 libhello.h ${DESTDIR}${PREFIX}/include

%.o: %.c %.h
	$(CC) -c $< -o $@ -Wall

libhello.so: libhello.o
	$(CC) -shared -o $@ $<
