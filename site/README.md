# The swindl website

The website of swindl, sjdbl and sil: what they are, a quick start, the guarantees, the
benchmarks, the example application, and the three references, online and as PDFs.

It is a [Hugo](https://gohugo.io) site, with the layout of SWL's site
(<https://swl.seecr.nl/>). The home page is `content/_index.md`, the introduction of the
benchmarks page `benchmarks.md`; the layout is in `layouts/`, the styles in
`static/css/site.css`. All other pages and the PDFs are made from the documentation in the
repositories (`make` does that); they are not in git:

| Page | From |
|---|---|
| `reference/`, `swindl-reference.pdf` | `../doc/reference.md` |
| `sjdbl/`, `sjdbl-reference.pdf` | `../../sjdbl/doc/reference.md` |
| `sil/`, `sil-reference.pdf` | `../../sil/doc/reference.md` |
| `guarantees/`, `webadapter/` | `../doc/guarantees.md`, `../doc/webadapter.md` |
| `benchmarks/` | `benchmarks.md` here, and `../benchmarks/RESULTS.md` |
| `example/` | `../examples/collection/README.md` |

sjdbl and sil are expected next to swindl (as in `~/development/seecr`); point elsewhere
with `make SJDBL_DIR=... SIL_DIR=...`. The versions on the pages are the latest tags.

## Building

You need `hugo` (extended, 0.120 or newer), `pandoc` (3.8 or newer) and `typst` (0.15 or
newer), as for SWL's site. On macOS: `brew install hugo pandoc typst`.

```sh
cd site
make          # site in public/, with the three PDFs
make serve    # dev server on http://localhost:1313/
make pdf      # only the PDFs
make clean
```

After new benchmark results (`benchmarks/RESULTS.md`), `make` again.

## Publishing

The site is at <https://swindl.seecr.nl/> (GitHub Pages; the domain is a CNAME for
`seecr.github.io`). `.github/workflows/pages.yml` builds and publishes it after every
release to PyPI, from the release tag, with sjdbl and sil at their default branch; run it
by hand (Actions > Publish website > Run workflow) after a change to the site or to the
docs of sjdbl or sil.
