# Benchmark results

Made with `PYTHONPATH=. python benchmarks/bench.py` (see its docstring for what is measured and how); the raw numbers are in `results.json`. Run it on your own machine: the numbers depend on the disk (every transaction is synced) and the CPU.

Measured 2026-11-16 on Intel(R) Xeon(R) Processor @ 2.10GHz, 2 CPUs, Linux-6.18.44-fc-v470-x86_64; Python 3.13.18, tantivy 0.27.0, SQLite 3.53.1. Median of repeated runs, in milliseconds.

### 10,000 records

| Question | hits | swindl | SQLite + FTS5 | swindl is |
|---|---:|---:|---:|---|
| text: a common word | 5,524 | 1.02 | 4.33 | **4.3x faster** |
| text: a rare word | 5 | 0.11 | 0.06 | 1.8x slower |
| text: two words | 1,839 | 0.96 | 1.61 | **1.7x faster** |
| prefix: 3 letters* | 3,552 | 2.33 | 3.30 | **1.4x faster** |
| filter genre, sort year desc | 1,394 | 0.38 | 0.08 | 4.6x slower |
| range of years, sort artist | 1,315 | 0.64 | 0.18 | 3.5x slower |
| text + drilldown (2 facets) | 5,524 | 1.39 | 9.11 | **6.5x faster** |
| page 50, sorted on year | 10,000 | 1.39 | 1.71 | **1.2x faster** |
| get one object by id | 1 | 0.02 | 0.01 | 1.8x slower |

| Writing | swindl | SQLite + FTS5 |
|---|---:|---:|
| change one object, searchable at once (ms) | 20 | 0.31 |
| change one object, index on the timer (ms) | 1.56 | - |
| load, transactions of 1,000 (objects/s) | 2,480 | 29,847 |
| rebuild the search index (s) | 0.87 | 0.01 |
| on disk (MB) | 5 files + 3 index | 4 |

### 100,000 records

| Question | hits | swindl | SQLite + FTS5 | swindl is |
|---|---:|---:|---:|---|
| text: a common word | 55,075 | 2.65 | 45 | **16.9x faster** |
| text: a rare word | 46 | 0.45 | 0.14 | 3.2x slower |
| text: two words | 17,979 | 1.96 | 15 | **7.8x faster** |
| prefix: 3 letters* | 35,430 | 7.57 | 35 | **4.7x faster** |
| filter genre, sort year desc | 13,867 | 0.77 | 0.28 | 2.7x slower |
| range of years, sort artist | 13,071 | 1.69 | 1.17 | 1.4x slower |
| text + drilldown (2 facets) | 55,075 | 3.42 | 113 | **33.0x faster** |
| page 50, sorted on year | 100,000 | 3.34 | 3.61 | **1.1x faster** |
| get one object by id | 1 | 0.02 | 0.01 | 1.3x slower |

| Writing | swindl | SQLite + FTS5 |
|---|---:|---:|
| change one object, searchable at once (ms) | 21 | 0.25 |
| change one object, index on the timer (ms) | 1.42 | - |
| load, transactions of 1,000 (objects/s) | 2,516 | 13,785 |
| rebuild the search index (s) | 8.15 | 0.19 |
| on disk (MB) | 48 files + 25 index | 44 |

