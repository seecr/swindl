swindl against SQLite with its full-text search (FTS5): the same data, the same questions,
both durable. SQLite is the yardstick everyone knows, and a very good one.

**The data** is a record collection: title, artist, label, genre, country, format, year and
notes, generated with a fixed seed. Words follow a Zipf distribution, as in real titles:
a few words are in many records, most in few.

**Fair on both sides.**

- Both are durable: swindl syncs every transaction to disk (`fsync`), SQLite runs in WAL
  mode with `synchronous=FULL`.
- Both answer with whole objects: swindl reads the page's objects from their JSON files,
  SQLite selects the page's rows. Both give the total number of hits.
- SQLite has an index for every filter and sort it is asked (genre + year, year, artist)
  and an FTS5 table over title, artist and label, kept up to date by triggers. swindl's
  model has the same fields in its `INDEX`.
- A facet ("text + drilldown") is one query for swindl; for SQLite it is the page, the
  count and a `GROUP BY` per facet.
- Timings are the median of 50 runs after a warm-up; the file system cache is warm for
  both.

**What it shows.** Where the question is about words (full text, prefixes, facets over
many hits), sil's index on tantivy is far ahead, and it gets further ahead as the data
grows. Where the question is an exact lookup or a sort on a B-tree index, SQLite is
faster; swindl answers those in a millisecond or two too, which is plenty for a web page.
Writing is SQLite's strong side: one file per object, synced, costs more than a row in a
page, and a change that must be searchable at once waits for tantivy's commit (most of
the 17-20 ms). With the default commit timer a change takes about a millisecond, and is
searchable within 5 seconds.

Run it yourself (the numbers depend most on your disk):

```sh
PYTHONPATH=. python benchmarks/bench.py
```

## Results

