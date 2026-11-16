# Collection: an example application on swindl

Keep track of what you collect: vinyl records, LEGO sets, anything. Built with
[SWL](https://github.com/seecr/swl) for the web side and swindl for the storage side
(sjdbl's files, sil's search). It is meant to be read: every part of swindl is used in a
real way, with comments that point to the rest.

What you can do in it:

- **"Do I have it?"** Type in the search box, in the shop: the results follow as you type
  (the last word is a prefix), over all your collections, by title, artist, catalogue or
  set number, format or tag.
- **Facets**: next to the results, how many items there are per artist, decade, format,
  condition and tag (sil's drilldown, over all hits). Click to filter, click again (or the
  chip) to remove.
- **Sort and page**: best match, recently added, title, artist, year. The url follows
  everything: reload or bookmark and you are back where you were.
- **Collections**: each of its own kind; the labels follow it ("Artist" and "Catalogue
  no." for records, "Theme" and "Set number" for LEGO). Delete one and all its items go,
  in one transaction.
- **Add and edit** in a dialog, checked by the WebAdapter: "nineteen" as a year gives
  "Should be a whole number" next to the field, with what you typed still there. The
  artist field suggests the artists already in the collection.
- **Import** a list (CSV, pasted): every row is checked as a form would be; one wrong
  value and nothing is imported.
- **Public**: make a collection public and share its page (`/c/<id>`), searchable,
  without login.
- **Users**: everyone keeps their own collections; the admin adds users (SWL's user
  screens).

## Running it

From the root of the swindl repository:

```sh
pip install -e .                       # swindl (with sjdbl and sil)
pip install -e examples/collection     # this example (and SWL)
python -m swindl_collection            # or: swindl-collection
```

Open <http://127.0.0.1:8000/> and log in as **demo** / **demo-password**. A few records
and LEGO sets are there to search. Everything is stored in `./collection-data` (change it
with `--data-dir`).

Run the tests with `pytest examples/collection/swindl_collection`.

## The files

```
examples/collection/
└── swindl_collection/
    ├── model.py          Collection and Item: FIELDS, INDEX, index_values, ADAPTATIONS
    ├── catalog.py        searching, deleting a collection, importing: no web in here
    ├── views.py          the actions (SWL): what the page asks the server
    ├── app.py            the store, SWL, the routes, login; the reindex step
    ├── demo.py           the demo data
    ├── app_test.py       tests, through the actions
    ├── templates/collection/   the page, the results, the facets, the dialogs
    └── static/           a few styles, and one small function
```

## How swindl is used

### One store, two models

`app.py` makes the store once:

```python
store = Store(data_dir / "data", MODELS, commit=Commit(immediate=True))
```

`data/store/` gets one JSON file per collection and item (sjdbl), `data/index/` an index
per model (sil). `Commit(immediate=True)`: a saved item is searchable at once, so "do I
have it?" right after adding it says yes. That costs some milliseconds per save; for an
application with many writes the default `Commit()` (every 5 seconds) is faster.

### The model says what is stored, searched and accepted

`model.py`, for an item:

- `FIELDS` (sjdbl): what is stored. `collection` is a reference (a `Proxy` until used),
  `tags` a list (`Field.json`), `price` a `Decimal`, `acquired` a date.
- `INDEX` and `index_values` (sil): what can be searched, sorted and counted. `all` is
  what the search box searches without a field name; `maker_exact`, `decade`, `format`,
  `condition` and `tag` are `drilldown=True` (the facets); `year`, `title_sort`,
  `maker_sort` and `created` are `sortable=True`. `decade` doesn't exist as a field: it is
  computed in `index_values`, which is where the index can differ from the data.
- `ADAPTATIONS` (the WebAdapter): how a form's text becomes values, with checks:
  `Adapt.int("year", checks=[at_least(1800), at_most(2100)])`, and `Adapt.custom` for the
  tags ("Jazz, blue note" becomes `["jazz", "blue note"]`).

### Searching: one query gives the page, the total and the facets

`catalog.search`:

```python
store.query(QueryParams(
    Item,
    query="+blue +no*",                          # what was typed; see search_text
    filters={"owner": "demo", "__archived__": "False", "decade": ["1950"]},
    sort=[{"field": "year", "reverse": True}],
    page=0, size=20,
    drilldown=[{"name": name, "count": 12} for name in FACETS],
))
```

Every search filters on `owner`, so you never see someone else's items, not even in a
count. A clicked facet value is one more filter term. The artist suggestions in the dialog
are a drilldown too (`catalog.maker_suggestions`): a prefix query on `maker`, counted per
`maker_exact`, so only your own artists are suggested.

### Changing: a put, or a transaction

A single save is `store.put(item)`: the file is written and synced, then the index
follows. More than one change that belongs together is a transaction:

```python
with store.transaction():                       # catalog.delete_collection
    for item in items:
        store.delete(item)
    store.delete(collection)
```

All of it is stored, or none of it: also when the server crashes halfway; it is finished
or undone when the store is opened again. The import does the same with its puts, after
checking every row first (`catalog.import_csv`).

### Ids from the outside are checked

Every qid that comes in with a request goes through `owned_collection` or `owned_item`:
`store.get(qid, assert_type=Item)` refuses a qid of another model (and sjdbl refuses
qids that are not a file of the store), and the owner must be you. Anything else is "no
longer exists".

### Reindexing is a step you take

When a new version changes `INDEX` or `index_values`, its CHANGELOG says so, and you leave
an empty file `<data dir>/actions/reindex` before starting it. `app.py` sees it, reindexes
from the files and removes it (`catalog.reindex_if_asked`). The application never decides
that by itself.

### Checking

`swindl-check collection-data/data swindl_collection.model:MODELS` tells whether the index
matches the files, without changing anything.
