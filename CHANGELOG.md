# Changelog

## 3.2.0 (2026-11-24)

### Changed

- Needs sil as `seecr-sil >= 3.4.0` (sil is on PyPI under that name; the import stays
  `sil`). In an existing virtualenv, `pip uninstall sil` first: both install the `sil`
  package.
- Needs sjdbl >= 0.6.0 and seecr-stdlib >= 0.7.0 (both on PyPI). lxml and tantivy,
  which swindl imports itself, are named as dependencies (they came with sjdbl and sil).
- setuptools-scm is no longer installed with swindl (it is only needed to build it);
  pytest, pytest-asyncio and pytest-xdist stay (the tests are part of the package). The
  dev tools (flake8, isort) are the `dev` dependency group in `pyproject.toml` (`pip install -e . --group dev`);
  `requirements-dev.txt` is gone.
- The package metadata names the license as an SPDX expression (`MIT`).

### Added

- Published on GitHub (https://github.com/seecr/swindl) and PyPI (`pip install
  swindl`): project URLs and classifiers in the metadata, tests in GitHub Actions, and a
  release to PyPI for every version tag.
- The website, https://swindl.seecr.nl/, with the references of swindl, sjdbl and sil,
  published after every release.

## 3.1.0 (2026-11-20)

### Added

- `swindl.oai`: OAI-PMH administration in the store (`Oai`, `OaiRecord`), as
  meresco-oai's OaiJazz: prefixes, hierarchical sets, deletes (in prefixes, in sets,
  `always_delete_in_prefixes`), unique increasing stamps, `select` for lists. See
  "OAI-PMH" in `doc/reference.md`.
- `swindl.oai.provider.OaiProvider`: OAI-PMH 2.0 provider for an `Oai`, as
  meresco-oai answered (XML, errors, resumption tokens), with x-wait; independent of a
  web framework. `delete_in_sets=False` leaves the setSpecs unmarked (as meresco's
  OaiPmh could); `about` may give `""` for an empty `<about>`.
- `swindl.oai.OaiDownloader`: harvests an OAI-PMH repository into the store, each part
  with its position in one transaction; x-wait or an interval; a parser of its own
  (`parser=`, e.g. `huge_tree`).
- `Store.on_transaction(listener)`: called with the changes after every transaction.
- `Store.sees_changes_at_once`: whether a search finds a change as soon as its
  transaction is done (`Commit(immediate=True)` or `Commit(on_search=True)`).

## 3.0.0 (2026-11-16)

Crash-safe transactions over files and index. Needs sjdbl 0.4.0 and sil 3.2.0.

**Reindex after upgrading** (`store.reindex(models)`, e.g. the `actions/reindex` file at
startup). sil 3.2.0 fixes a bug that could leave an old version of an updated object in
the index next to the new one (it then shows twice in a list); the reindex removes those.
And an index with a `sortable=True` text or untokenized field changes schema (faster
sorting) and starts empty until it is reindexed.

### License

- swindl is now MIT licensed (was GPLv2), like SWL. So are sjdbl (0.4.0) and sil
  (3.2.0).

### Breaking changes

- `Store.batch()` is replaced by `Store.transaction()`: all puts and deletes of the block
  are stored together at its end, or none of them. A failing block now stores nothing
  (with `batch()` its puts stayed in the files and the index).
- swindl commits the indexes itself; sil's own commit task is not used any more.
  `Indexes.deferred_commit()` is gone (`Indexes.deferred()` is its replacement inside
  swindl).

### Added

- `Store.transaction()`. See "Transactions" in `doc/reference.md`.
- `Store.commit()`: commit the indexes now (for `Commit(timeout=0)`).
- `Commit(on_search=True)`: a save commits nothing; the next search commits first, so
  it finds everything saved before it. Many saves without a search in between share one
  commit: for harvesting, or many updates at once. A change then costs about a
  millisecond instead of a commit.
- Crash safety. The files have a transaction completely or not at all (sjdbl 0.4.0), and
  the index catches up: the qids of a transaction go to `index/pending.log` before the
  files are committed and leave it after the index has committed them; when the store is
  opened, what is still in it is indexed again from the files. See "After a crash".
- `swindl-check <data dir> <models>`: reports whether the index matches the files
  (and leftovers of a crash, unreadable files, dangling references). Changes nothing.
- `doc/guarantees.md`: what swindl promises, what not, the limits, backups.
- `tools/crashtest.py`: kills a process running transactions at random moments, many
  times, and checks after each kill.
- `Store.reindex()` commits once at the end (it used to commit after every object with
  `Commit(immediate=True)`).

### Upgrading from 2.x

- `with store.batch():` becomes `with store.transaction():`. Code that relied on the puts
  of a failing block being kept should catch the exception inside the block.
- A subclass of `Store` that overrides `batch()` overrides `transaction()` instead.
- Within a transaction other threads no longer see its changes through `get()` before
  the block ends.

### Changed

- The wheel only has the package itself (`swindl/`); it used to install `doc/`, `examples/` and
  other directories of the repository into site-packages too.

## 2.2.1 (2026-11-16)

### Fixed

- Changes from several threads (plain `def` endpoints run in Starlette's thread pool) are
  safe: `put()`, `delete()` and `reindex()` hold one lock around the files and the index.
  Before, a slow thread could give the index older values than the files had, and the
  cache of indexed values could raise a `KeyError`.
- `query()`, `list()` and `find_by_field()` skip a hit whose file is gone (deleted
  between the search and the read, or left in the index by a crash between the file
  delete and the index delete). They used to return `None` among the objects.

## 2.2.0 (2026-11-10)

### Added

- `Store.delete()` also takes a reference to an object (sjdbl's `Proxy`, as references and
  collections give) or its qid, and deletes it from the files and the index without
  loading it. A reference used to fail ("No qid found"), and a qid deleted the file but
  then failed before the index. For an object nothing changes.

## 2.1.0 (2026-11-10)

Needs sil 3.1.0 (for `Index.deferred_commit`) and sjdbl 0.3.1.

**Reindex after upgrading** when a model has an `IndexField.int`: sil 3.1.0 makes int fields
fast fields (a range query reads the column), which changes the index schema. An existing
index with int fields is recreated empty; rebuild it with `store.reindex(models)` (e.g. the
`actions/reindex` file at startup, see "Reindexing" in `doc/reference.md`).

### Added

- `Store.batch()`: a block of puts with one commit of the index at its end, instead of one
  per put (`Commit(immediate=True)`). Hundreds of puts go from seconds to under one. Within
  the block queries don't see its puts yet; a delete is still committed at once. See
  "Storing" in `doc/reference.md`.

## 2.0.0 (2026-11-06)

A new WebAdapter: a form saves only what it sends, empty dates and numbers can be
cleared, and wrong values give an error per field instead of a crash. See
`doc/webadapter.md`. Needs sjdbl 0.3.0.

### Breaking changes

- `swindl.webadapter` is rewritten; its API is new (see "Upgrading from 1.x").
- `swindl.store.Base` is swindl's own subclass of sjdbl's `Base`, with `INDEX = []` and
  `ADAPTATIONS = []`. sjdbl 0.3.0 no longer has `INDEX`: a model built on sjdbl's `Base`
  directly gets no index any more.
- Raised at import, when the model class is defined: an `Adapt` for a name that is not a
  field, a field adapted twice (swindl), and a field name used twice or clashing with an
  attribute of `Base` such as `id`, `qid` or `update` (sjdbl 0.3.0).

### Added

- `from_form(model, form, fields, obj=None, adaptations=None)`: the converted and checked
  values of a form, for `update` or `create`. Not sent is left alone (a checkbox is
  `False`), empty is `None` (text: `""`), all errors in one `FormErrors`.
- `to_form(obj, fields, form=None, adaptations=None)`: the values for the inputs of a
  form, or with `form=` what was typed, to show a form again after errors.
- Checks `at_least`, `at_most`, `max_length` and `one_of`; `FieldError(code, **params)`
  for checks of your own.
- `Adapt.custom(name, from_web(obj, form), to_web(obj, value))`.
- `doc/reference.md`, `examples/` and this changelog.

### Upgrading from 1.x

Pin `swindl >= 1.2, < 2` until an application is converted; an application that pins swindl
without an upper bound should get `< 2` first.

- Import `Base` from `swindl.store`, not from `sjdbl.base`, for every model that is indexed
  or has `ADAPTATIONS`.
- `WebAdapter.adapt(obj, form, fields)` becomes `from_form(type(obj), form, fields,
  obj=obj)`.
- The wrapper `WebAdapter(obj)` is gone: use `to_form(obj, fields)` for form inputs, and
  template filters (`format_date`, `format_number`) on the object to show values.
- `Adapt.method(name, from_web, to_web)` becomes `Adapt.custom(name, from_web, to_web)`;
  `from_web` now gets `(obj, form)` and `to_web` `(obj, value)`.
- Not sent is left alone, empty is `None`, and wrong values raise `FormErrors`: a view that
  saves a form catches `FormErrors` and shows the form again with
  `to_form(obj, fields, form=form)` and the errors. A workaround that only passes the
  fields that were sent is no longer needed.
- Error messages are the application's: translate `error.code` with `error.params`.
- An `Adapt` that names no field, and a field name that clashes with `Base`, now raise at
  import: fix the name.
