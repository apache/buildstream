# Makefile for updating BuildStream's requirements files.
#

REQUIREMENTS_IN := $(wildcard *.in)
REQUIREMENTS_TXT := $(REQUIREMENTS_IN:.in=.txt)
PYTHON := python3
VENV := $(PYTHON) -m venv

VENV_PIP = $(VENVDIR)/bin/pip


.PHONY: all FORCE

all: $(REQUIREMENTS_TXT)

%.txt: %.in FORCE
	$(eval VENVDIR := $(shell mktemp -d $(CURDIR)/.bst-venv.XXXXXX))
	$(VENV) $(VENVDIR)
	$(VENV_PIP) install wheel
	$(VENV_PIP) install -r $<
	$(VENV_PIP) freeze -r $< | grep -v pkg-resources > $@
	rm -rf $(VENVDIR)

FORCE:
