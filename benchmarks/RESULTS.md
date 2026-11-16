# Benchmark results

Measured 2026-11-16 on arm, 10 CPUs, macOS-26.6.2-arm64-arm-64bit-Mach-O; Python 3.15.2, tantivy 0.27.0, SQLite 3.54.1, PostgreSQL 17.12, Meilisearch 1.57.0. Full syncs (macOS): SQLite with fullfsync, PostgreSQL with wal_sync_method=fsync_writethrough, as tantivy does; sjdbl's files with a plain fsync. Median of repeated runs, in milliseconds; the fastest in bold.

### 10,000 records

| Question | hits | swindl | SQLite + FTS5 | PostgreSQL | Meilisearch |
|---|---:|---:|---:|---:|---:|
| text: a common word | 5,509 | 0.73 | 2.77 | 3.31 | **0.70** |
| text: a rare word | 5 | 0.12 | **0.07** | 0.19 | 0.43 |
| text: two words | 1,837 | **0.69** | 1.04 | 1.10 | 0.76 |
| prefix: 3 letters* | 3,548 | 1.66 | 2.10 | 1.77 | **0.74** |
| filter genre, sort year desc | 1,394 | 0.44 | **0.05** | 0.23 | 0.58 |
| range of years, sort artist | 1,315 | 0.51 | **0.11** | 0.17 | 0.63 |
| text + drilldown (2 facets) | 5,509 | **0.79** | 6.43 | 6.04 | 0.83 |
| page 50, sorted on year | 10,000 | **0.80** | 0.86 | 2.59 | 11 |
| get one object by id | 1 | 0.03 | **0.01** | 0.07 | 0.14 |

| Writing | swindl | SQLite + FTS5 | PostgreSQL | Meilisearch |
|---|---:|---:|---:|---:|
| change one object, searchable at once (ms) | 82 | **3.91** | 4.00 | 22 |
| change one object, index on the timer (ms) | **0.81** | - | - | - |
| change one object, index committed by the next search (ms) | **0.46** | - | - | - |
| load, transactions of 1,000 (objects/s) | 4,265 | **39,415** | 18,633 | 22,618 |
| rebuild the search index (s) | 0.8 | **0.01** | 0.02 | - |
| on disk (MB) | 8 | **4** | 6 | 23 |
| what you run | nothing: a library | nothing: a library | a database server | a search server, and a store for the data |

### 100,000 records

| Question | hits | swindl | SQLite + FTS5 | PostgreSQL | Meilisearch |
|---|---:|---:|---:|---:|---:|
| text: a common word | 55,071 | 1.33 | 31 | 16 | **0.72** |
| text: a rare word | 46 | 0.44 | **0.11** | 0.24 | 0.64 |
| text: two words | 17,975 | 0.98 | 9.62 | 10 | **0.72** |
| prefix: 3 letters* | 35,423 | 4.27 | 21 | 19 | **0.78** |
| filter genre, sort year desc | 13,867 | 0.55 | **0.20** | 0.57 | 0.62 |
| range of years, sort artist | 13,071 | 1.01 | 0.80 | 0.70 | **0.69** |
| text + drilldown (2 facets) | 55,071 | 1.71 | 70 | 35 | **1.08** |
| page 50, sorted on year | 100,000 | **1.59** | 1.88 | 5.08 | 11 |
| get one object by id | 1 | 0.10 | **0.01** | 0.08 | 0.15 |

| Writing | swindl | SQLite + FTS5 | PostgreSQL | Meilisearch |
|---|---:|---:|---:|---:|
| change one object, searchable at once (ms) | 93 | **3.96** | 3.99 | 23 |
| change one object, index on the timer (ms) | **0.89** | - | - | - |
| change one object, index committed by the next search (ms) | **0.69** | - | - | - |
| load, transactions of 1,000 (objects/s) | 3,622 | 15,029 | **23,596** | 17,359 |
| rebuild the search index (s) | 12.6 | **0.11** | 0.12 | - |
| on disk (MB) | 72 | **44** | 57 | 167 |
| what you run | nothing: a library | nothing: a library | a database server | a search server, and a store for the data |

