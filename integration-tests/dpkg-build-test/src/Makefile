
build:
	$(shell touch foo)

install: build
	install -d $(DESTDIR)/usr/share
	install -m 0644 foo $(DESTDIR)/usr/share/foo

all: build install
