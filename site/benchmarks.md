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

**What it shows.**

- **Questions about words** (full text, prefixes, facets over many hits) split the field
  in two. Meilisearch and swindl answer in about a millisecond, also at 100,000 records;
  the databases take tens of milliseconds there, up to a hundred with facets, and get
  slower as the data grows. Meilisearch, made for exactly this, is fastest on most of
  them; swindl is a close second, without a server.
- **Exact lookups and sorts on a B-tree index** are SQLite's: fastest, with everyone
  else within a millisecond. A deep page (page 50) is where Meilisearch is slow.
- **Writing** is the databases' strong side. One file per object, synced, costs more
  than a row in a page, and a change that must be searchable at once waits for
  tantivy's commit. With the default commit timer a change takes about a millisecond,
  and is searchable within 5 seconds. With `Commit(on_search=True)` a change takes
  under a millisecond too, and the next search commits first (one commit for all the
  changes before it; that search pays it, which this row leaves out): for changes in
  bursts, it is the fastest way to write that never gives a stale answer.
- **What you run**: swindl and SQLite are libraries. PostgreSQL is a server to install,
  secure, back up and upgrade. Meilisearch is a server too, and only an index: your data
  still needs a store next to it, kept in step.

**On macOS**, a plain `fsync` does not flush the drive's own cache; a full sync
(`F_FULLFSYNC`) does, and costs tens of milliseconds. tantivy always does a full sync, so
on macOS the benchmark makes SQLite (`fullfsync`) and PostgreSQL
(`wal_sync_method = fsync_writethrough`, set for the run and set back after) do the
same, for writes that are equally durable. sjdbl's files use a plain `fsync`, as the
databases do by default; that is swindl's "index on the timer" row. On Linux, `fsync`
flushes the drive's cache and all of this doesn't apply.

Run it yourself (the numbers depend most on your disk). PostgreSQL and Meilisearch are
included when you give their address:

```sh
PYTHONPATH=. python benchmarks/bench.py \
    --postgres "host=/tmp dbname=postgres" \
    --meilisearch http://127.0.0.1:7700 --meilisearch-key <master key>
```

## Results

