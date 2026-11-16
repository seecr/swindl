swindl against what you would otherwise use, on the same data, with the same questions,
all of them durable:

- **SQLite with FTS5**: a library too, and the yardstick everyone knows.
- **PostgreSQL** with its full-text search: what most applications would use instead,
  with a database server to install, secure, back up and upgrade.
- **Meilisearch**, a search server made for as-you-type search with facets, when it is
  included (see below): fast search, but your data still needs a store next to it.

**The data** is a record collection: title, artist, label, genre, country, format, year and
notes, generated with a fixed seed. Words follow a Zipf distribution, as in real titles:
a few words are in many records, most in few.

**Fair to every side.**

- All are durable: swindl syncs every transaction to disk (`fsync`); SQLite runs in WAL
  mode with `synchronous=FULL`; PostgreSQL with `synchronous_commit` on; a Meilisearch
  write is waited for until its task is done.
- All answer with whole objects (the page of 20) and the total number of hits.
- Each has an index for every filter and sort it is asked (genre + year, year, artist),
  and full-text search over title, artist and label: an FTS5 table kept up to date by
  triggers; a generated `tsvector` column with a GIN index; Meilisearch's own index with
  the filters, sorts and facets declared and typo tolerance off. swindl's model has the
  same fields in its `INDEX`.
- PostgreSQL gets what a careful application would do: `VACUUM ANALYZE` after the bulk
  load (until then its GIN index keeps new entries in a pending list, and a rare word
  took 4 ms instead of 0.4), and a plan per query (a cached generic plan, made for a
  common word, scanned everything for a rare one).
- A facet ("text + drilldown") is one query for swindl and Meilisearch; for SQLite and
  PostgreSQL it is the page, the count and a `GROUP BY` per facet.
- Timings are the median of 50 runs after a warm-up; caches are warm for all. PostgreSQL
  runs on the same machine, over a Unix socket.

**What it shows.** Where the question is about words (full text, prefixes, facets over
many hits), sil's index on tantivy is far ahead of both databases, and gets further ahead
as the data grows: at 100,000 records a search with two facets takes 3 ms against about
100. Where the question is an exact lookup or a sort on a B-tree index, SQLite is
fastest; swindl answers those in a millisecond or two, which is plenty for a web page.
Writing is the databases' strong side: one file per object, synced, costs more than a
row in a page, and a change that must be searchable at once waits for tantivy's commit
(most of the 17-20 ms). With the default commit timer a change takes 1-2 ms, and is
searchable within 5 seconds.

Run it yourself (the numbers depend most on your disk). PostgreSQL and Meilisearch are
included when you give their address:

```sh
PYTHONPATH=. python benchmarks/bench.py \
    --postgres "host=/tmp dbname=postgres" \
    --meilisearch http://127.0.0.1:7700 --meilisearch-key <master key>
```

## Results

