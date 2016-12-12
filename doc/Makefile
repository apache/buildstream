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

# Canned recipe for generating plugin api skeletons
#   $1 = the plugin directory
#   $2 = the output docs directory
#
# Explanation:
#
#   Sphinx does not have any option for skipping documentation,
#   we dont want to document plugin code because nobody uses that
#   but we do want to use module-level docstrings in plugins in
#   order to explain how plugins work.
#
#   For this purpose, we replace sphinx-apidoc with a simple
#   makefile rule which generates a template slightly differently
#   from how sphinx does it, allowing us to get what we want
#   from plugin documentation.
#
define plugin-doc-skeleton
	@for file in $$(find ${1} -name "*.py"); do 		\
	    base=$$(basename $$file);				\
	    modname=$${base%.py};				\
	    echo -n "Generating ${2}/$${modname}.rst... ";	\
	    sed -e "s|@@MODULE@@|$${modname}|g" 		\
		source/plugin.rsttemplate > 			\
                ${2}/$${modname}.rst.tmp && 			\
		mv ${2}/$${modname}.rst.tmp ${2}/$${modname}.rst || exit 1; \
	    echo "Done."; \
	done
endef


.PHONY: apidoc
apidoc:
	mkdir -p source/elements
	mkdir -p source/sources
	sphinx-apidoc --separate -o source $(CURDIR)/../buildstream
	$(call plugin-doc-skeleton,$(CURDIR)/../buildstream/plugins/elements,source/elements)
	$(call plugin-doc-skeleton,$(CURDIR)/../buildstream/plugins/sources,source/sources)

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

