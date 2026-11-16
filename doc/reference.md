# swindl reference

swindl (Seecr Web Index and Database Lib) is the storage side of an SWL application. It
keeps objects in [sjdbl](https://github.com/seecr/sjdbl)'s JSON files and makes them
searchable with [sil](https://github.com/seecr/sil)'s index, as one `Store`. It also has the
WebAdapter, which turns the text of an HTML form into the typed values of an object and
back. This page lists what swindl provides. For a guided introduction, run and read the
examples first; this page is for looking things up:

```sh
PYTHONPATH=. python examples/store.py        # storing, searching, revisions, archive
PYTHONPATH=. python examples/webadapter.py   # forms: converting, checking, errors
```

- [Setting up a store](#setting-up-a-store)
- [Models](#models)
- [Storing](#storing)
- [Transactions](#transactions)
- [After a crash](#after-a-crash)
- [Searching](#searching)
- [Reindexing](#reindexing)
- [Checking: swindl-check](#checking-swindl-check)
- [Forms: the WebAdapter](#forms-the-webadapter)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

## Setting up a store

```python
from swindl.store.store import Store
from swindl.store.indexes import Commit

store = Store(data_dir, models=[Customer, Order])     # once, at startup
...
store.disconnect()                                     # at shutdown: closes the indexes
```

`data_dir` is a `pathlib.Path`. The store keeps the objects in
`data_dir/store/<Model>/<id>.json` (sjdbl) and an index per model in
`data_dir/index/<Model>` (sil). Both directories are made when they are missing.

`commit` says when changes become searchable:

| | |
|---|---|
| `Commit()` (default) | within 5 seconds (`Commit(timeout=...)`); many puts share a commit. Needs a running event loop when the store is made (the timer is an asyncio task) |
| `Commit(immediate=True)` | at the end of every put, delete or transaction: searchable at once; for tests, scripts and examples |
| `Commit(timeout=0)` | only at `disconnect()` (or `store._indexes.commit()`); for bulk imports |

A `get` always reads the files, so it sees a change at once either way; only queries wait for
the commit. A delete is committed at once (at the end of its transaction).

## Models

A model is a subclass of `swindl.store.Base`: sjdbl's `Base` with `INDEX` and
`ADAPTATIONS` (see [Forms](#forms-the-webadapter)). It has its fields and, for searching,
its index fields and their values:

```python
from sil.indexfield import IndexField
from sjdbl.field import Field
from swindl.store import Base

class Book(Base):
    FIELDS = Base.FIELDS + [
        Field.str("title"),
        Field.str("genre"),
        Field.int("year"),
        Field.str("note"),                              # stored, not indexed
    ]
    INDEX = Base.INDEX + [
        IndexField.unqualified("all"),                  # for a query without field name
        IndexField.text("title"),
        IndexField.untokenized("genre", drilldown=True),
        IndexField.int("year", sortable=True),
    ]

    def index_values(self):                             # called at every put
        values = super().index_values()
        values.update(all=f"{self.title} {self.genre}", title=self.title,
                      genre=self.genre, year=self.year)
        return values
```

The field types (`Field.str`, `date`, `datetime`, `decimal`, `bool`, `enum`, `json`,
`reference`, ...) are sjdbl's; see its README. When the class is defined, a field name used
twice or one of `Base`'s attributes (`id`, `qid`, `update`, ...) raises a `TypeError`.
Every index also has `__id__` and `__archived__` (the text `"True"` or `"False"`), added
by swindl.

| Index field | For |
|---|---|
| `IndexField.untokenized(name)` | exact values: codes, ids, statuses; filters |
| `IndexField.text(name)` | words: searched per word, lowercased |
| `IndexField.int(name)` | numbers |
| `IndexField.unqualified(name)` | the field a query without `field:` searches |

Options: `sortable=True`, `drilldown=True` (counts per value), `stored=True`,
`suggest=True`.

## Storing

```python
book = store.create(Book, dict(title="Dune", year=1965))   # makes and puts
book = Book.create(title="Dune"); store.put(book)          # the same in two steps

book = store.get("Book:<id>")                  # None when not there or archived
book.update(year=1966)                         # True when something changed
store.put(book)                                # files and index
store.archive(book)                            # hidden from get and list
store.delete(book)                             # gone, from files and index
```

| | |
|---|---|
| `create(cls, values=None)` | a new object from a dict, put; `cls` may be the name |
| `put(*objs)` | stores the objects and indexes them |
| `get(qid_or_qrid, include_archived=False, assert_type=None)` | the object, or `None` |
| `archive(obj)` | marks it archived and puts it |
| `delete(obj)` | removes it from the files and the index; `obj` may also be a reference to one (a `Proxy`, as references and collections give; nothing is loaded) or its qid |
| `enumerator(...)` | sjdbl's `Enumerator`, for sequential numbers |
| `transaction()` | a block whose puts and deletes are stored together, or not at all; see [Transactions](#transactions) |
| `disconnect()` | commits and closes the indexes |

**qid and qrid.** `obj.qid` is `"Book:<id>"`; `obj.qrid` adds the revision,
`"Book:<id>:<rev>"`. The revision changes at every put. `get(qrid)` raises
`HasChangedException` (from `swindl.store.store`) when the object was changed since: put the
qrid in a form, and you know whether someone else saved in between.

`assert_type=Book` raises `TypeError` when the qid is of another model; use it for qids that
come from a request.

A put whose indexed values did not change (only `note`, say) writes the file but leaves the
index alone, and does not wait for a commit.

## Transactions

Every put and delete is a transaction of its own. A `transaction()` block makes one of
several:

```python
with store.transaction():
    order.update(state="paid")
    store.put(order, invoice)
    store.delete(basket)
# stored, all of it; and indexed
```

- At the end of the block everything is stored together, or nothing is: an exception in
  the block discards it (files and index unchanged, the objects get their old revisions
  back), and a crash halfway is finished or undone when the store is opened again (see
  [After a crash](#after-a-crash)).
- Within the block, `get` sees its puts and deletes (in this thread; other threads see
  them when the block is done). `list`, `query`, `find_one` and `find_by_field` don't: they
  search the index, which follows at the end.
- The store's lock is held for the whole block: changes from other threads wait. Keep
  blocks short in a web application.
- Blocks can be nested; the outermost one commits.
- It is also the fast way to store many objects: one sync of the files and one commit of
  the index for the whole block, instead of one per put.

```python
with store.transaction():
    for order in customer.orders:      # e.g. after a rename: their index changes
        store.put(store.get(order.qid))
```

## After a crash

The files are the truth and the index is derived from them, so swindl makes sure of two
things when the process (or the machine) dies:

1. **The files have a transaction completely or not at all.** sjdbl writes the new
   versions to temporary files first, and with more than one file it commits by writing
   `store/commit.log`. A commit that was interrupted is finished when the store is opened;
   temporary files of a transaction that never committed are removed.
2. **The index catches up.** Before the files are committed, the qids of the transaction go
   to `index/pending.log`; after the index has committed them they are removed. When the
   store is opened, the objects still in it are indexed again from the files (a qid
   without a file is removed from the index). With the default `Commit()` this also covers
   the changes of the last seconds before a crash that were not committed yet.

Both are logged as a warning and need nothing from the application. This is not a reindex:
only what the crash left unfinished is done. `swindl-check` shows beforehand what opening
will do. See `doc/guarantees.md` for what is promised, and what is not.

## Searching

```python
from swindl.store.store import QueryParams

result = store.query(QueryParams(
    "Book",
    query="*",                                      # everything; or e.g. "title:dune"
    filters={"genre": "fantasy"},                   # exact terms, all must match
    sort=[{"field": "year", "reverse": True}],      # or "year", or a list of those
    page=0, size=20,
    drilldown=[{"name": "genre", "count": 10}],
))
result.objs                  # the objects of this page
result.total                 # all hits
result.drilldown             # {"genre": [("fantasy", 2)]}
```

**The query** uses sil's syntax (tantivy): words, `field:word`, `"a phrase"`, `AND`/`OR`,
`prefix*`. Words without a field search the `unqualified` index field. A query that is not
valid syntax (a stray quote from a search box) is searched for literally.

**Filters** are exact terms on index fields; a list as value means one term per value, all
of them must match (so for a field with one value, a list finds nothing). On a `text`
field a term is one lowercased word (`title="dune"`).
`Query` from `swindl.store.indexes` is the query with its terms, when you build it yourself:

```python
q = Query("lord")
q.add_term("genre", "fantasy")
store.query(QueryParams("Book", query=q))
```

**Sorting** only on `sortable=True` fields; equal values (and no sort with `"*"`) keep the
order in which the objects were indexed. With a query and no sort, the best matches come first.

**The result** (`QueryResult`):

| | |
|---|---|
| `objs` | the objects of this page |
| `total` | the number of hits (in the index; a hit whose file is gone is left out of `objs` but still counted) |
| `start`, `stop` | the numbers of the first and last hit of this page, from 1 |
| `pages.first`, `.prev`, `.next`, `.last` | page numbers, `None` where there is none |
| `is_last_page()` | |
| `params` | the `QueryParams`; change `page` and query again for the next page |
| `drilldown` | per drilldown field a list of `(value, count)`, most first |

**Shortcuts**:

| | |
|---|---|
| `list(cls, include_archived=False, **filters)` | a generator over all pages |
| `find_one(cls, **filters)` | the first hit or `None` |
| `find_by_field(cls, field, value)` | the objects with this term (one page) |

`query`, `find_one` and `find_by_field` do **not** leave out archived objects; `list` does. Add
`filters={"__archived__": "False"}` to a query that should not show them.

## Reindexing

`store.reindex(models)` empties the indexes and indexes every object of the given models
again from the files. It is needed after a change to a model's `INDEX` or `index_values`, and
only then. swindl never does it by itself, and application code doesn't either: the
application offers it as an explicit step, e.g. a file `<data>/actions/reindex` that the
server checks at startup, and the CHANGELOG of the release says when to do it. When a
model's index fields changed, sil starts that index empty and logs that it needs a reindex.

## Checking: swindl-check

```sh
swindl-check <data dir> <module>:<list of models>     # or <module>: all models in it
swindl-check /data/myapp myapp.models:ALL_MODELS
```

Reports, one per line, whether the index matches the files, and changes nothing (it does
not even open a `Store`, so it can run next to the application):

- leftovers of a crash: `store/commit.log`, `.tmp` files, objects in `index/pending.log`
  (opening the store finishes them);
- objects indexed without a file, files that are not indexed, objects indexed twice;
- index values that differ from the file (for `untokenized` and `int` index fields);
- files that are not valid JSON, references to objects that don't exist.

Exit code 0 and `ok` when all is well, 1 otherwise. In code: `swindl.check.check(data_dir,
models)` gives the list.

## Forms: the WebAdapter

`swindl.webadapter` converts and checks what comes in from a web form, and gives the values
for the inputs of a form. The full description is in `doc/webadapter.md`; this is the
summary.

```python
from swindl.webadapter import Adapt, FormErrors, at_least, from_form, max_length, to_form

class Person(Base):
    FIELDS = [Field.str("name"), Field.date("dob"), Field.int("age"),
              Field.bool("active", default=False)]
    ADAPTATIONS = [                              # a field without an Adapt is text
        Adapt.str("name", checks=[max_length(100)]),
        Adapt.date("dob"),
        Adapt.int("age", checks=[at_least(0)]),
        Adapt.bool("active"),
    ]

fields = ["name", "dob", "active"]
try:
    person.update(**from_form(Person, form, fields, obj=person))
except FormErrors as e:
    values = to_form(person, fields, form=form)  # what was typed; e.errors per field
```

The rules, per field: not in `fields`, never touched; not sent, left alone (a checkbox:
`False`); sent, stripped, and empty becomes `None` (text: `""`); then converted
(`invalid_int`, `invalid_decimal`, `invalid_date`) and checked.

| | |
|---|---|
| `from_form(model, form, fields, obj=None, adaptations=None)` | the values, or `FormErrors` with all errors |
| `to_form(obj, fields, form=None, adaptations=None)` | the values for the inputs (`None` is `""`); with `form=` what was typed |
| `Adapt.str`, `.int`, `.decimal(decimals=2)`, `.date`, `.bool` | with `checks=[...]`, and `from_web`/`to_web` to replace the conversion |
| `Adapt.custom(name, from_web(obj, form), to_web(obj, value))` | anything else; `obj` is `None` when creating |
| `at_least(n)`, `at_most(n)`, `max_length(n)`, `one_of(values)` | checks: `too_small`, `too_large`, `too_long`, `not_allowed` |
| `FieldError(code, **params)` | a wrong value; raise it in a check of your own |
| `FormErrors.errors` | field name → `FieldError` (`.code`, `.params`); the application translates |

`adaptations` adds or overrides `Adapt`s for one form, e.g. `one_of` with a list from the
store. swindl's `Base` checks at class definition that every `Adapt` names a field.

## Testing

Use `Commit(immediate=True)` so queries see a put at once, and pytest's `tmp_path`:

```python
def test_find(tmp_path):
    store = Store(tmp_path, [Book], commit=Commit(immediate=True))
    store.create(Book, dict(title="Dune"))
    assert store.find_one(Book, title="dune").title == "Dune"
```

The WebAdapter needs no store: a model with `ADAPTATIONS` and a dict as form will do
(`swindl/webadapter_test.py`).

## Troubleshooting

| | |
|---|---|
| A query doesn't find what was just put | commit: within 5 seconds, or `Commit(immediate=True)`; within a `transaction()`, at its end |
| `RuntimeError: no running event loop` when making the store | the default `Commit()` starts a timer: make the store in the application's startup, or use `Commit(immediate=True)` / `Commit(timeout=0)` in scripts |
| A warning about `commit.log` or `pending.log` at startup | the process died during a transaction; it was finished, nothing to do |
| Archived objects in a query | `query` doesn't leave them out; filter on `__archived__: "False"` |
| A filter on a text field finds nothing | it is one lowercased word: `title="dune"`, not `"Dune"` |
| `RuntimeError: Unsortable field` | add `sortable=True` to the index field; then reindex |
| A changed `INDEX` gives old results | reindex: it is not done by itself |
| A field is not searchable | it needs an `INDEX` field and a value from `index_values`; then reindex |
| A checkbox is saved as off by a form that doesn't show it | it is in `fields`; list only what the form has |
| `TypeError` at import: Adapt for ..., which is not a field | a typo in `ADAPTATIONS`, or the field is missing from `FIELDS` |
| A model gets no index | it is built on sjdbl's `Base`; use `swindl.store.Base` |
| `HasChangedException` | someone saved the object since the qrid was taken; get it again |
