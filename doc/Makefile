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

# Fix for when python is mapped to python2 not python3
# This is an issue in the sphinx-build script provided in the default install
# because it uses the generic python env, so we need to have a copy of this script
# but with an explicit call to python3.
#
# Why python3? We are using some features of sphinx that are only implemented
# currently in python3
#
PYV=$(shell python -c "import sys;t='{v[0]}'.format(v=list(sys.version_info[:2]));sys.stdout.write(t)")

ifeq ($(PYV), 2)
	SPHINXBUILD = ./sphinx-build3
endif

.PHONY: all templates html devhelp

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
	@for file in $$(find ${1} -name "*.py" ! -name "__init__.py"); do \
	    base=$$(basename $$file);					\
	    module=${2}.$${base%.py};					\
	    modname=$${base%.py};					\
	    echo -n "Generating source/${2}/$${modname}.rst... ";	\
	    sed -e "s|@@MODULENAME@@|$${modname}|g" 			\
	        -e "s|@@MODULE@@|$${module}|g" 				\
		source/plugin.rsttemplate > 				\
                source/${2}/$${modname}.rst.tmp && 			\
		mv source/${2}/$${modname}.rst.tmp source/${2}/$${modname}.rst || exit 1; \
	    echo "Done."; \
	done
endef

# We set PYTHONPATH here because source/conf.py sys.modules hacks dont seem to help sphinx-build import the plugins
all: html devhelp

# Generate rst templates for the docs using a mix of sphinx-apidoc and
# our 'plugin-doc-skeleton' routine for plugin pages.
templates:
	mkdir -p source/elements
	mkdir -p source/sources
	sphinx-apidoc --force --separate --module-first --no-headings -o source $(CURDIR)/../buildstream
	$(call plugin-doc-skeleton,$(CURDIR)/../buildstream/plugins/elements,elements)
	$(call plugin-doc-skeleton,$(CURDIR)/../buildstream/plugins/sources,sources)

# Targets which generate docs with sphinx build
#
#
html devhelp: templates
	@echo "Building $@..."
	PYTHONPATH=$(CURDIR)/../buildstream/plugins \
	    $(SPHINXBUILD) -b $@ $(ALLSPHINXOPTS) "$(BUILDDIR)/$@" \
	    $(wildcard source/*.rst) \
	    $(wildcard source/elements/*.rst) \
	    $(wildcard source/sources/*.rst)
	@echo
	@echo "Build of $@ finished, output: $(CURDIR)/$(BUILDDIR)/$@"

testy:
	@echo "Using $(SPHINXBUILD)"
	@echo "Py is $(PYV)"
