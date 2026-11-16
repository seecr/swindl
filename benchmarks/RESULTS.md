# Benchmark results

Measured 2026-11-16 on arm, 10 CPUs, macOS-26.6.2-arm64-arm-64bit-Mach-O; Python 3.15.2, tantivy 0.27.0, SQLite 3.54.1, PostgreSQL 17.12, Meilisearch 1.57.0. Full syncs (macOS): SQLite with fullfsync, PostgreSQL with wal_sync_method=fsync_writethrough, as tantivy does; sjdbl's files with a plain fsync. Median of repeated runs, in milliseconds; the fastest in bold.

### 10,000 records

| Question | hits | swindl | SQLite + FTS5 | PostgreSQL | Meilisearch |
|---|---:|---:|---:|---:|---:|
| text: a common word | 5,524 | 0.91 | 2.61 | 3.87 | **0.75** |
| text: a rare word | 5 | 0.12 | **0.06** | 0.20 | 0.42 |
| text: two words | 1,839 | **0.64** | 0.98 | 0.97 | 0.71 |
| prefix: 3 letters* | 3,552 | 1.53 | 1.98 | 1.64 | **0.70** |
| filter genre, sort year desc | 1,394 | 0.41 | **0.05** | 0.23 | 0.56 |
| range of years, sort artist | 1,315 | 0.46 | **0.11** | 0.16 | 0.57 |
| text + drilldown (2 facets) | 5,524 | **0.71** | 5.89 | 5.71 | 0.74 |
| page 50, sorted on year | 10,000 | **0.74** | 0.79 | 2.44 | 9.39 |
| get one object by id | 1 | 0.02 | **0.00** | 0.08 | 0.17 |

| Writing | swindl | SQLite + FTS5 | PostgreSQL | Meilisearch |
|---|---:|---:|---:|---:|
| change one object, searchable at once (ms) | 83 | **4.00** | 4.00 | 25 |
| change one object, index on the timer (ms) | **0.74** | - | - | - |
| load, transactions of 1,000 (objects/s) | 4,548 | **41,348** | 19,761 | 22,864 |
| rebuild the search index (s) | 0.46 | **0.01** | 0.02 | - |
| on disk (MB) | 8 | **4** | 6 | 24 |
| what you run | nothing: a library | nothing: a library | a database server | a search server, and a store for the data |

### 100,000 records

| Question | hits | swindl | SQLite + FTS5 | PostgreSQL | Meilisearch |
|---|---:|---:|---:|---:|---:|
| text: a common word | 55,075 | 1.41 | 30 | 14 | **0.71** |
| text: a rare word | 46 | 0.39 | **0.11** | 0.29 | 0.59 |
| text: two words | 17,979 | 0.95 | 9.55 | 9.50 | **0.65** |
| prefix: 3 letters* | 35,430 | 4.07 | 21 | 17 | **0.70** |
| filter genre, sort year desc | 13,867 | 0.51 | **0.20** | 0.62 | 0.56 |
| range of years, sort artist | 13,071 | 0.93 | 0.79 | 0.75 | **0.65** |
| text + drilldown (2 facets) | 55,075 | 1.67 | 68 | 31 | **1.05** |
| page 50, sorted on year | 100,000 | **1.60** | 1.78 | 4.98 | 11 |
| get one object by id | 1 | 0.10 | **0.01** | 0.09 | 0.16 |

| Writing | swindl | SQLite + FTS5 | PostgreSQL | Meilisearch |
|---|---:|---:|---:|---:|
| change one object, searchable at once (ms) | 88 | **3.56** | 3.95 | 25 |
| change one object, index on the timer (ms) | **0.88** | - | - | - |
| load, transactions of 1,000 (objects/s) | 3,603 | 14,983 | **23,270** | 18,032 |
| rebuild the search index (s) | 12.29 | **0.11** | **0.11** | - |
| on disk (MB) | 72 | **44** | 57 | 169 |
| what you run | nothing: a library | nothing: a library | a database server | a search server, and a store for the data |

