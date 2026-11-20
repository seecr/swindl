# swindl – Seecr Web Index and Database Lib

The storage side of an SWL application: sjdbl's JSON files (objects) and sil's index
(searching) behind one `Store`, plus the WebAdapter that converts and checks what comes
in from a web form. MIT licensed. Maintained by Seecr (Johan Jonkers, Thijs Janssen).
`doc/reference.md` is the user-facing reference; keep it in step with the code.

## Layout

- `swindl/store/base.py` – `Base`: sjdbl's `Base` with `INDEX` and `ADAPTATIONS`; checks
  at class definition that every `Adapt` names a field. Models import it from
  `swindl.store`.
- `swindl/store/store.py` – `Store` (create/put/get/list/query/find_one/find_by_field/
  archive/delete/transaction/reindex, recovery at open), `QueryParams`, `QueryResult`,
  `Pages`, `HasChangedException`
- `swindl/store/indexes.py` – `Indexes` (one sil `Index` per model with an `INDEX`; does
  the commits itself), `Commit` (when changes become searchable), `PendingLog`, `Query`
  (query text plus exact terms)
- `swindl/oai/` – OAI-PMH: `repository.py` (`Oai`, `OaiRecord`, `OaiRepository`:
  OaiJazz's administration in the store; keep its semantics, they are what meresco
  clients got), `provider.py` (`OaiProvider`: meresco-oai's XML, errors and tokens; x-wait
  wakes requests from `Store.on_transaction` via `loop.call_soon_threadsafe`, with a
  change counter so a change between select and wait is not missed), `downloader.py`
  (`OaiDownloader`: a part and its position in one transaction; the in-memory state is
  reloaded when that transaction fails)
- `swindl/check.py` – `swindl-check`: index vs files, crash leftovers, dangling
  references. Only reads (no Store, no recovery); keep it that way.
- `site/` – the website of swindl, sjdbl and sil (Hugo; pages and PDFs made from the
  docs of the three repositories, see `site/README.md`)
- `benchmarks/bench.py` – swindl against SQLite + FTS5 on the same data; results in
  `benchmarks/RESULTS.md` (not in the package)
- `tools/crashtest.py` – SIGKILLs a process running transactions, hundreds of times;
  run before a release that touches the commit path (not in the package)
- `doc/guarantees.md` – what is promised and what not; keep it in step with the code
- `swindl/store/crash_test.py` – real crashes (a child process that `os._exit`s) at each
  step of a transaction
- `swindl/webadapter.py` – `from_form`, `to_form`, `Adapt`, the checks (`at_least`,
  `at_most`, `max_length`, `one_of`), `FieldError`, `FormErrors`
- `swindl/store/dump.py` – `swindl-load-sdbl-dump`: converts an old sdbl dump. Transient,
  for migrations only; keep it out of the reference.
- `doc/reference.md` – the reference; `doc/webadapter.md` – the WebAdapter in full
  (principles, rules, a complete view, why no library); `CHANGELOG.md` – keep it updated,
  with "Upgrading" notes for breaking changes
- `examples/` – runnable scripts, explained step by step (`store.py`, `webadapter.py`)
- `examples/collection/` – an example application (SWL + swindl): collections of records,
  LEGO sets; its own pyproject and README. Generic names only, no customer projects.

## Commands

```sh
pytest swindl                                  # the tests (-n5: pytest-xdist)
flake8 swindl examples tools && isort --check-only swindl examples tools
PYTHONPATH=. python examples/store.py          # an example against this checkout
PYTHONPATH=. python examples/webadapter.py
pytest examples/collection/swindl_collection    # needs swl: pip install -e examples/collection
PYTHONPATH=. python tools/crashtest.py --rounds 500   # before a release of the commit path
```

`env/` is the virtualenv (see the seecr-python rebuild-venv skill), with
`requirements-dev.txt` (flake8, isort); sjdbl and sil come from Seecr's devpi. To work
against a local sjdbl checkout: `pip install -e ../sjdbl`.

## Design decisions (deliberate, don't re-propose)

- Explicit over implicit, KISS. No reindex in application code because a model changed:
  a reindex is an explicit step (announced in the CHANGELOG, done via `actions/reindex`,
  i.e. `store.reindex(models)`), and swindl only reports that one is needed
  (`needs_reindex`). Finishing an interrupted commit from the commit log at startup is
  part of a transaction, not a reindex. No adaptations derived from `FIELDS`.
- Fields define the model; the WebAdapter guards the boundary. No web or check knowledge
  in sjdbl's `Field`, no conversions derived from `Field`s. `update`/`create` trust their
  input; checking is the WebAdapter's.
- The WebAdapter (design in `doc/webadapter.md`, agreed November 2026) stays our own;
  WTForms, Pydantic and marshmallow were considered and don't fit. Its rules, per field:
  not in `fields`, never touched; not sent, left alone, except a checkbox (`False`); sent,
  stripped, empty is `None` (text `""`); then converted (`invalid_<type>`) and checked.
  `Adapt.custom` gets `(obj, form)` and decides. All errors in one `FormErrors`.
- Forms only: `to_form` gives values for inputs; showing values is template filters. No
  wrapper object around models.
- Simple data: results and errors are plain dicts; errors are a code and params, without
  messages. swindl does not translate and does not depend on SWL.
- Choices are the check `one_of(values)`, built where the values are known (the model for
  a fixed list, the view for a list from the store). No `choices=` argument.

## Invariants to keep

- Every change is a transaction (`put`/`delete` alone are one each), with `Store._lock`
  held: qids to `index/pending.log` (synced) → sjdbl commits the files → the index
  changes → commit (immediate, or the timer) → `pending.log` emptied. The pending log is
  only emptied by `Indexes.commit()`, which holds the same lock, so never in the middle of
  a transaction. At open, `Store._recover` indexes the pending qids again from the files.
- sil's own commit task is off (`commit_timeout=0`); swindl's `Indexes` runs the timer
  (`asyncio.to_thread(self.commit)`) and commits only indexes with changes.
- A delete is committed at the end of its transaction, except with `on_search`.
- `Commit(on_search=True)`: no commit after a change; every search method of `Indexes`
  calls `_commit_before_search()` first (commits all changed indexes and empties the
  pending log, under the lock). A new search method must call it too.
- `put()` stores in sjdbl and then indexes. `Indexes.add_record` skips the index when the
  indexed values of that object did not change since the last put (bounded cache,
  `INDEXED_CACHE_SIZE`; forgetting only means indexing again).
- Every index has `__id__` and `__archived__` (`"True"`/`"False"`) besides the model's
  `INDEX`; `list()` filters on `__archived__`, `query()` does not.
- `get()` reads the files, never the index; `query()` gets ids from the index and reads the
  objects from the files.
- `get(qrid)` raises `HasChangedException` when the revision on disk differs.

## Conventions

- Every source file starts with the Swindl license header (copy it from
  `swindl/webadapter.py`); `doc/license.conf` describes it.
- Code style: black, isort with the black profile (`pyproject.toml`), flake8 (`.flake8`);
  lines up to 88.
- Before every push: flake8, isort and the tests must pass. The pre-push hook
  (`.githooks/pre-push`, on with `git config core.hooksPath .githooks`, once per clone)
  runs them and stops the push otherwise; `git push --no-verify` skips it.
- Tests live next to the code (`*_test.py`), are plain pytest functions and use `tmp_path`
  and `Commit(immediate=True)` for stores.

## Working agreements

- Python >= 3.11. Versions come from git tags via `setuptools_scm` (`2.0.0`);
  `swindl/_version.py` is generated. Don't tag or push unless asked.
- Report behaviour changes and anything left undone.
- Known loose ends: `QueryResult.summary` is Dutch text that can't be translated.
