# Makefile for Sphinx documentation
#

# You can set these variables from the command line.
SPHINXOPTS    =
SPHINXBUILD   = sphinx-build
PAPER         =
BUILDDIR      = build

# Internal variables.
PAPEROPT_a4     = -D latex_paper_size=a4
PAPEROPT_letter = -D latex_paper_size=letter
ALLSPHINXOPTS   = -d $(BUILDDIR)/doctrees $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) source
# the i18n builder cannot share the environment and doctrees with the others
I18NSPHINXOPTS  = $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) source

all: docs

.PHONY: apidoc
apidoc:
	mkdir -p source/elements
	mkdir -p source/sources
	sphinx-apidoc --separate -o source $(CURDIR)/../buildstream
	sphinx-apidoc --separate -o source/elements $(CURDIR)/../buildstream/plugins/elements
	sphinx-apidoc --separate -o source/sources $(CURDIR)/../buildstream/plugins/sources

# We set PYTHONPATH here because source/conf.py sys.modules hacks dont seem to help sphinx-build import the plugins
.PHONY: docs
docs: apidoc
	PYTHONPATH=$(CURDIR)/../buildstream/plugins/sources:$(CURDIR)/../buildstream/plugins/elements \
	    $(SPHINXBUILD) -b html $(ALLSPHINXOPTS) $(BUILDDIR)/html \
	    $(wildcard source/*.rst) \
	    $(wildcard source/elements/*.rst) \
	    $(wildcard source/sources/*.rst)
	@echo
	@echo "Build finished. The HTML pages are in $(BUILDDIR)/html."

