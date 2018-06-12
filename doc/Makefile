# Makefile for Sphinx documentation
#

# Note, due to a problem with python2/python3 parallel
# installability of sphinx (https://github.com/sphinx-doc/sphinx/issues/4375)
# we dont use the standard `sphinx-build` and `sphinx-apidoc` entry points.
#
# The following technique works as long as sphinx is installed for python3,
# regardless of the entry point which might be in /usr/bin or PATH, but
# will stop working in sphinx >= 2.0. Hopefully by then, the mentioned
# bug will be fixed and we can use a standard python3 specific script to
# invoke sphnix.
#
SPHINXOPTS    =
SPHINXBUILD   = python3 -m sphinx
SPHINXAPIDOC  = python3 -m sphinx.apidoc
PAPER         =
BUILDDIR      = build

# Internal variables.
PAPEROPT_a4     = -D latex_paper_size=a4
PAPEROPT_letter = -D latex_paper_size=letter
ALLSPHINXOPTS   = -W -d $(BUILDDIR)/doctrees $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) source
# the i18n builder cannot share the environment and doctrees with the others
I18NSPHINXOPTS  = $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) source

BST2HTML = $(CURDIR)/bst2html.py

.PHONY: all clean templates templates-clean html devhelp

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
	@for file in $$(find ${1} -name "*.py" ! -name "_*.py"); do	\
	    base=$$(basename $$file);					\
	    module=${2}.$${base%.py};					\
	    modname=$${base%.py};					\
	    echo -n "Generating source/${2}/$${modname}.rst... ";	\
	    sed -e "s|@@MODULE@@|$${module}|g" 				\
		source/plugin.rsttemplate > 				\
                source/${2}/$${modname}.rst.tmp && 			\
		mv source/${2}/$${modname}.rst.tmp source/${2}/$${modname}.rst || exit 1; \
	    echo "Done."; \
	done
endef



# We set PYTHONPATH here because source/conf.py sys.modules hacks dont seem to help sphinx-build import the plugins
all: html devhelp

clean: templates-clean
	rm -rf build

# Generate rst templates for the docs using a mix of sphinx-apidoc and
# our 'plugin-doc-skeleton' routine for plugin pages.
templates:
	mkdir -p source/elements
	mkdir -p source/sources
	$(SPHINXAPIDOC) --force --separate --module-first --no-headings --no-toc -o source $(CURDIR)/../buildstream
	$(call plugin-doc-skeleton,$(CURDIR)/../buildstream/plugins/elements,elements)
	$(call plugin-doc-skeleton,$(CURDIR)/../buildstream/plugins/sources,sources)

# Generate the html fragments of colorized BuildStream terminal output only
# if they don't yet exist. This is expensive so you need to run `make clean` first
# if you want to regenerate them.
#
SESSION_HTML = $(patsubst sessions/%.run,source/sessions/%.html,$(wildcard sessions/*.run))
source/sessions/%.html:
	$(BST2HTML) -o $@ --description $(patsubst source/sessions/%.html,sessions/%.run,$@)

templates-clean:
	rm -rf source/elements
	rm -rf source/sources
	rm -rf source/sessions

# Targets which generate docs with sphinx build
#
#
html devhelp: templates $(SESSION_HTML)
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
