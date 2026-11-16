# The website of swindl, sjdbl and sil (Hugo), with their references as pages and PDFs.
#
#   make            build everything into public/
#   make serve      run the Hugo dev server (http://localhost:1313/)
#   make pdf        only the reference PDFs
#
# The pages come from the documentation in the repositories: swindl (..), and sjdbl and
# sil next to it (../../sjdbl, ../../sil, as gclone puts them; change with SJDBL_DIR=...
# and SIL_DIR=...). The versions are the latest tags. Extra Hugo options go in
# HUGO_FLAGS, e.g. `make serve HUGO_FLAGS="--bind 0.0.0.0"`.

SWINDL_DIR ?= ..
SJDBL_DIR ?= ../../sjdbl
SIL_DIR ?= ../../sil

version = $(shell git -C $(1) describe --tags 2>/dev/null || echo main)
SWINDL_VERSION = $(call version,$(SWINDL_DIR))
SJDBL_VERSION = $(call version,$(SJDBL_DIR))
SIL_VERSION = $(call version,$(SIL_DIR))

PAGES := content/reference.md content/sjdbl.md content/sil.md content/guarantees.md \
         content/webadapter.md content/benchmarks.md content/example.md
PDFS := static/swindl-reference.pdf static/sjdbl-reference.pdf static/sil-reference.pdf

.PHONY: all build serve pages pdf clean

all: build

build: pages pdf
	hugo --minify $(HUGO_FLAGS)

serve: pages pdf
	hugo server $(HUGO_FLAGS)

pages: $(PAGES)
pdf: $(PDFS)

# A page: front matter, then the document. page.sh <title> <library> <version> <pdf>
# <source url> <markdown file>
define page
	sh page.sh "$(1)" "$(2)" "$(3)" "$(4)" "$(5)" $(6) > $@
endef

GITHUB := https://github.com/seecr

content/reference.md: $(SWINDL_DIR)/doc/reference.md page.sh
	$(call page,swindl reference,swindl,$(SWINDL_VERSION),swindl-reference.pdf,$(GITHUB)/swindl/blob/main/doc/reference.md,$<)
content/sjdbl.md: $(SJDBL_DIR)/doc/reference.md page.sh
	$(call page,sjdbl reference,sjdbl,$(SJDBL_VERSION),sjdbl-reference.pdf,$(GITHUB)/sjdbl/blob/main/doc/reference.md,$<)
content/sil.md: $(SIL_DIR)/doc/reference.md page.sh
	$(call page,sil reference,sil,$(SIL_VERSION),sil-reference.pdf,$(GITHUB)/sil/blob/main/doc/reference.md,$<)
content/guarantees.md: $(SWINDL_DIR)/doc/guarantees.md page.sh
	$(call page,What swindl promises,swindl,$(SWINDL_VERSION),,$(GITHUB)/swindl/blob/main/doc/guarantees.md,$<)
content/webadapter.md: $(SWINDL_DIR)/doc/webadapter.md page.sh
	$(call page,The WebAdapter,swindl,$(SWINDL_VERSION),,$(GITHUB)/swindl/blob/main/doc/webadapter.md,$<)
content/example.md: $(SWINDL_DIR)/examples/collection/README.md page.sh
	$(call page,An example application,swindl,$(SWINDL_VERSION),,$(GITHUB)/swindl/tree/main/examples/collection,$<)
# the benchmarks: how they are made (benchmarks.md, here) and the results of the last run
content/benchmarks.md: benchmarks.md $(SWINDL_DIR)/benchmarks/RESULTS.md page.sh
	{ cat benchmarks.md; sed '1,/^Measured/{/^Measured/!d}' $(SWINDL_DIR)/benchmarks/RESULTS.md; } \
	    > benchmarks.tmp.md
	$(call page,Benchmarks,swindl,$(SWINDL_VERSION),,$(GITHUB)/swindl/tree/main/benchmarks,benchmarks.tmp.md)
	rm benchmarks.tmp.md

# The PDFs: pandoc turns a reference into Typst with pdf/reference.typ as template (title
# page, contents, styles), then typst makes the PDF. The title and the hand-made table of
# contents of the reference are left out; the template makes both. reference.lua keeps
# each example on one page with the sentence that introduces it, and marks header rows.
define pdf
	awk 'NR == 1 && /^# / { next } /^- \[[^]]*\]\(#[^)]*\)$$/ { next } { print }' $(1) | \
	pandoc --from markdown+gfm_auto_identifiers-raw_html-raw_tex-tex_math_dollars-smart \
	    --shift-heading-level-by=-1 \
	    --to typst --template pdf/reference.typ --syntax-highlighting=idiomatic \
	    --lua-filter pdf/reference.lua \
	    --variable library="$(2)" --variable version="$(3)" --variable tagline="$(4)" \
	    --output pdf/$(2).out.typ
	typst compile --ignore-system-fonts pdf/$(2).out.typ $@
endef

PDF_DEPS := pdf/reference.typ pdf/reference.lua pdf/seecr-logo.png

static/swindl-reference.pdf: $(SWINDL_DIR)/doc/reference.md $(PDF_DEPS)
	$(call pdf,$<,swindl,$(SWINDL_VERSION),crash-safe storage and fast search for Python web apps)
static/sjdbl-reference.pdf: $(SJDBL_DIR)/doc/reference.md $(PDF_DEPS)
	$(call pdf,$<,sjdbl,$(SJDBL_VERSION),Python objects as plain JSON files, with crash-safe transactions)
static/sil-reference.pdf: $(SIL_DIR)/doc/reference.md $(PDF_DEPS)
	$(call pdf,$<,sil,$(SIL_VERSION),a search index with facets and suggestions, on tantivy)

clean:
	rm -rf public resources $(PAGES) $(PDFS) pdf/*.out.typ benchmarks.tmp.md .hugo_build.lock
