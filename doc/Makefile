# Makefile for Sphinx documentation
#

# Note, due to a problem with python2/python3 parallel
# installability of sphinx (https://github.com/sphinx-doc/sphinx/issues/4375)
# we dont use the standard `sphinx-build` and `sphinx-apidoc` entry points.
#
# The following technique works as long as sphinx is installed for python3,
# regardless of the entry point which might be in /usr/bin or PATH.
#
# Since Sphinx 2.0 is planned to be Python 3-only, this workaround should not
# be needed once Spinx 2.0 is released, and we upgrade to it
#
SPHINXOPTS    =
SPHINXBUILD   = python3 -m sphinx
SPHINXAPIDOC  = python3 -m sphinx.ext.apidoc
PAPER         =
BUILDDIR      = build

# Internal variables.
PAPEROPT_a4     = -D latex_paper_size=a4
PAPEROPT_letter = -D latex_paper_size=letter
ALLSPHINXOPTS   = -W -d $(BUILDDIR)/doctrees $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) source
# the i18n builder cannot share the environment and doctrees with the others
I18NSPHINXOPTS  = $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) source

# Set BST_FORCE_SESSION_REBUILD to force rebuild the docs
BST2HTML = $(CURDIR)/bst2html.py
BST2HTMLOPTS =
ifneq ($(strip $(BST_FORCE_SESSION_REBUILD)),)
BST2HTMLOPTS = --force
endif

# Help Python find buildstream and its plugins
PYTHONPATH=$(CURDIR)/..:$(CURDIR)/../src/buildstream/plugins


.PHONY: all clean templates templates-clean sessions sessions-prep sessions-clean badges badges-clean html devhelp

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


all: html devhelp

clean: templates-clean sessions-clean badges-clean
	rm -rf build

############################################################
#                 Plugin doc templates                     #
############################################################

# Generate rst templates for the docs using a mix of sphinx-apidoc and
# our 'plugin-doc-skeleton' routine for plugin pages.
templates:
	mkdir -p source/elements
	mkdir -p source/sources
	$(SPHINXAPIDOC) --force --separate --module-first --no-headings --no-toc -o source $(CURDIR)/../src/buildstream *_pb2*.py
	$(call plugin-doc-skeleton,$(CURDIR)/../src/buildstream/plugins/elements,elements)
	$(call plugin-doc-skeleton,$(CURDIR)/../src/buildstream/plugins/sources,sources)

templates-clean:
	rm -rf source/elements
	rm -rf source/sources

############################################################
#                   Session captures                       #
############################################################

# Stage the stored sessions into the place where they will
# be used in the build.
#
# This is separated so that the git tree does not become
# dirty as a result of a documentation build process - which
# messes up the docs version number and the version number
# printed in some command line output.
#
sessions-prep:
	mkdir -p source/sessions
	cp source/sessions-stored/*.html source/sessions

# bst2html is called unconditionally for every session file in SESSION_FILES.
#
# By default, this will generate the html fragments of colorized BuildStream terminal
# output only if the output html files don't yet exist.
#
# Specify BST_FORCE_SESSION_REBUILD=1 to force rebuild all session html files.
#
SESSION_FILES=$(wildcard sessions/*.run)
$(SESSION_FILES): sessions-prep

%.run:
	PYTHONPATH=$(PYTHONPATH) $(BST2HTML) $(BST2HTMLOPTS) $@

sessions: $(SESSION_FILES)

sessions-clean:
	rm -rf source/sessions


############################################################
# Generate release badges and their redirecting html pages #
############################################################
badges-clean:
	rm -rf source/badges

badges:
	mkdir -p source/badges
	$(CURDIR)/badges.py > source/badges/snapshot.svg
	$(CURDIR)/badges.py --release > source/badges/release.svg
	$(CURDIR)/badges.py --redirect > source/badges/snapshot.html
	$(CURDIR)/badges.py --redirect --release > source/badges/release.html


############################################################
#                    Main sphinx build                     #
############################################################

# Targets which generate docs with sphinx build
#
#
html devhelp: templates sessions badges
	@echo "Building $@..."
	PYTHONPATH=$(PYTHONPATH) \
	    $(SPHINXBUILD) -b $@ $(ALLSPHINXOPTS) "$(BUILDDIR)/$@" \
	    $(wildcard source/*.rst) \
	    $(wildcard source/tutorial/*.rst) \
	    $(wildcard source/developing/*.rst) \
	    $(wildcard source/handling-files/*.rst) \
            $(wildcard source/junctions/*.rst) \
	    $(wildcard source/examples/*.rst) \
	    $(wildcard source/elements/*.rst) \
	    $(wildcard source/sources/*.rst) \
	    $(wildcard source/hacking/*.rst)
	@echo
	@echo "Build of $@ finished, output: $(CURDIR)/$(BUILDDIR)/$@"
# Makefile for Sphinx documentation
#
