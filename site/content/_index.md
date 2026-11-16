---
title: "swindl"
---

## introduction

swindl is the storage side of a Python web application: your objects in plain JSON files,
searchable through a real search index, as one `Store`. No database server, no ORM, no
migrations of a schema you never wanted.

It is three small libraries that work together:

- **[sjdbl](sjdbl/)** keeps every object as an indented JSON file, with revisions
  against lost updates and **crash-safe transactions**.
- **[sil](sil/)** is a search index on [tantivy](https://github.com/quickwit-oss/tantivy):
  a forgiving query language, sorting, facets (drilldown) and suggestions.
- **[swindl](reference/)** puts them behind one `Store` that keeps the index in step with
  the files, and adds the WebAdapter, which turns form input into checked values.

It is made for the same software as [SWL](https://swl.seecr.nl/), its web side: admin
screens, registries, catalogues, case files. Data that people search, filter and edit all
day, in amounts from a few thousand to a few hundred thousand objects per kind.

## motivation

- Why does an application that serves a few dozen users need a database server to
  install, secure, back up and upgrade?
- Why can't you just `cat` a record, `grep` the data or fix one value by hand?
- Why does search with facets (counts per value) need yet another server next to it?
- Why should a crash at the wrong moment leave half a change behind?

Keep the data in files a person can read, make every change all-or-nothing, and let a
real search engine, in process, answer the questions. That is swindl.

## quick start

```sh
pip install swindl
```

A model says what is stored and what can be searched:

```python
from sil.indexfield import IndexField
from sjdbl.field import Field
from swindl.store import Base, Store
from swindl.store.indexes import Commit
from swindl.store.store import QueryParams


class Record(Base):
    FIELDS = Base.FIELDS + [Field.str("title"), Field.str("artist"), Field.int("year")]
    INDEX = Base.INDEX + [
        IndexField.unqualified("all"),
        IndexField.untokenized("artist_exact", drilldown=True),
        IndexField.int("year", sortable=True),
    ]

    def index_values(self):
        values = super().index_values()
        values.update(all=f"{self.title} {self.artist}", artist_exact=self.artist,
                      year=self.year)
        return values


store = Store(data_dir, [Record], commit=Commit(immediate=True))

with store.transaction():                     # all of it, or none of it
    store.put(Record.create(title="Kind of Blue", artist="Miles Davis", year=1959))
    store.put(Record.create(title="Blue Train", artist="John Coltrane", year=1958))

result = store.query(QueryParams(
    Record, query="blue", sort="year", drilldown=[{"name": "artist_exact"}]))
result.total                                  # 2
[r.title for r in result.objs]                # ['Blue Train', 'Kind of Blue']
result.drilldown                              # {'artist_exact': [('John Coltrane', 1), ...]}
```

On disk: `data_dir/store/Record/<id>.json`, one readable file per record, and
`data_dir/index/Record/`, the search index, which can always be rebuilt from the files.

## what you get

- **Plain files.** Every object is an indented JSON file: read it, grep it, diff it, back
  it up with a copy.
- **Crash-safe transactions.** `with store.transaction():` stores all its puts and deletes,
  or none. A crash halfway is finished or undone when the store is opened again, and the
  index catches up by itself. [What is promised, and what not](guarantees/).
- **No lost updates.** Every object has a revision; saving a stale copy raises instead of
  overwriting someone else's change.
- **Real search.** Words, phrases, prefixes, ranges and `field:value`, best matches first;
  sorting on several fields with stable paging; facets with counts over all hits.
  [Fast, too](benchmarks/): on 100,000 records a full-text search with two facets takes
  3 ms.
- **Forms.** The [WebAdapter](webadapter/) converts and checks what comes in from a form,
  and gives one error per field instead of a crash.
- **`swindl-check`** tells whether the index matches the files, and changes nothing.
- **Threads are safe**; one process per data directory.

## docs {#docs}

- [swindl reference](reference/) ([pdf](swindl-reference.pdf)): the `Store`, models,
  transactions, searching, the WebAdapter, checking.
- [sjdbl reference](sjdbl/) ([pdf](sjdbl-reference.pdf)): the files, revisions,
  references, transactions and crash safety.
- [sil reference](sil/) ([pdf](sil-reference.pdf)): index fields, the query language,
  sorting, drilldown, suggestions.
- [What swindl promises](guarantees/): atomicity, durability, the limits, backups.
- [Benchmarks](benchmarks/): against SQLite with FTS5.
- [An example application](example/): keep track of your records (or LEGO), on SWL and
  swindl; every part of swindl used in a real way.
- Sources: [swindl]({{< param github >}}), [sjdbl]({{< param sjdbl >}}),
  [sil]({{< param sil >}}).

## history

swindl grew out of Seecr's work on search systems that harvest, enrich and index data.
Its predecessor stored objects with SQLAlchemy in MySQL, which became slow with larger
data sets and needed a database server next to every application. sjdbl replaced it with
plain files; sil replaced Lucene, through a JVM, with tantivy, in process. What is left is
small enough to understand completely.

<figure class="quote">
<blockquote>Simplicity is a great virtue but it requires hard work to achieve it and education to appreciate it. And to make matters worse: complexity sells better.</blockquote>
<figcaption>Edsger W. Dijkstra, <a href="https://www.cs.utexas.edu/~EWD/transcriptions/EWD08xx/EWD896.html">EWD 896</a> (1984)</figcaption>
</figure>
