# Benchmark results

Made with `PYTHONPATH=. python benchmarks/bench.py` (see its docstring for what is measured and how); the raw numbers are in `results.json`. Run it on your own machine: the numbers depend on the disk (every transaction is synced) and the CPU.

Measured 2026-11-16 on Intel(R) Xeon(R) Processor @ 2.10GHz, 2 CPUs, Linux-6.18.44-fc-v470-x86_64; Python 3.13.18, tantivy 0.27.0, SQLite 3.53.1. Median of repeated runs, in milliseconds.

### 10,000 records

| Question | hits | swindl | SQLite + FTS5 | swindl is |
|---|---:|---:|---:|---|
| text: a common word | 5,524 | 1.89 | 4.42 | **2.3x faster** |
| text: a rare word | 5 | 0.25 | 0.06 | 4.0x slower |
| text: two words | 1,839 | 1.41 | 1.58 | **1.1x faster** |
| prefix: 3 letters* | 3,552 | 3.00 | 3.25 | **1.1x faster** |
| filter genre, sort year desc | 1,394 | 0.93 | 0.08 | 11.5x slower |
| range of years, sort artist | 1,315 | 1.47 | 0.18 | 8.1x slower |
| text + drilldown (2 facets) | 5,524 | 1.91 | 10 | **5.5x faster** |
| page 50, sorted on year | 10,000 | 1.92 | 1.75 | 1.1x slower |
| get one object by id | 1 | 0.04 | 0.01 | 3.5x slower |

| Writing | swindl | SQLite + FTS5 |
|---|---:|---:|
| change one object, searchable at once (ms) | 17 | 0.38 |
| change one object, index on the timer (ms) | 1.27 | - |
| load, transactions of 1,000 (objects/s) | 2,506 | 27,521 |
| rebuild the search index (s) | 1.0 | 0.02 |
| on disk (MB) | 5 files + 3 index | 4 |

### 100,000 records

| Question | hits | swindl | SQLite + FTS5 | swindl is |
|---|---:|---:|---:|---|
| text: a common word | 55,075 | 3.43 | 48 | **14.1x faster** |
| text: a rare word | 46 | 0.89 | 0.14 | 6.2x slower |
| text: two words | 17,979 | 2.54 | 15 | **6.0x faster** |
| prefix: 3 letters* | 35,430 | 8.80 | 34 | **3.9x faster** |
| filter genre, sort year desc | 13,867 | 1.18 | 0.35 | 3.4x slower |
| range of years, sort artist | 13,071 | 4.54 | 1.21 | 3.8x slower |
| text + drilldown (2 facets) | 55,075 | 3.24 | 106 | **32.8x faster** |
| page 50, sorted on year | 100,000 | 3.21 | 3.48 | **1.1x faster** |
| get one object by id | 1 | 0.04 | 0.01 | 3.2x slower |

| Writing | swindl | SQLite + FTS5 |
|---|---:|---:|
| change one object, searchable at once (ms) | 21 | 0.34 |
| change one object, index on the timer (ms) | 1.13 | - |
| load, transactions of 1,000 (objects/s) | 2,551 | 12,896 |
| rebuild the search index (s) | 8.15 | 0.15 |
| on disk (MB) | 48 files + 24 index | 44 |

