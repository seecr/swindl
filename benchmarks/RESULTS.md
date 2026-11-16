# Benchmark results

Made with `PYTHONPATH=. python benchmarks/bench.py` (see its docstring for what is measured, how, and how to include PostgreSQL and Meilisearch); the raw numbers are in `results.json`. Run it on your own machine: the numbers depend on the disk (every transaction is synced) and the CPU.

Measured 2026-11-16 on Intel(R) Xeon(R) Processor @ 2.10GHz, 2 CPUs, Linux-6.18.44-fc-v470-x86_64; Python 3.13.18, tantivy 0.27.0, SQLite 3.53.1, PostgreSQL 16.15. Median of repeated runs, in milliseconds; the fastest in bold.

### 10,000 records

| Question | hits | swindl | SQLite + FTS5 | PostgreSQL |
|---|---:|---:|---:|---:|
| text: a common word | 5,524 | **1.16** | 4.46 | 7.47 |
| text: a rare word | 5 | 0.12 | **0.06** | 0.39 |
| text: two words | 1,839 | **1.04** | 1.53 | 3.09 |
| prefix: 3 letters* | 3,552 | **2.76** | 2.90 | 4.36 |
| filter genre, sort year desc | 1,394 | 0.48 | **0.07** | 0.28 |
| range of years, sort artist | 1,315 | 0.69 | **0.14** | 0.52 |
| text + drilldown (2 facets) | 5,524 | **1.48** | 10 | 14 |
| page 50, sorted on year | 10,000 | **1.44** | 1.83 | 2.16 |
| get one object by id | 1 | 0.02 | **0.01** | 0.11 |

| Writing | swindl | SQLite + FTS5 | PostgreSQL |
|---|---:|---:|---:|
| change one object, searchable at once (ms) | 20 | **0.17** | 0.60 |
| change one object, index on the timer (ms) | **1.39** | - | - |
| load, transactions of 1,000 (objects/s) | 2,478 | **29,912** | 18,022 |
| rebuild the search index (s) | 0.81 | **0.01** | 0.02 |
| on disk (MB) | 8 | **4** | 6 |
| what you run | nothing: a library | nothing: a library | a database server |

### 100,000 records

| Question | hits | swindl | SQLite + FTS5 | PostgreSQL |
|---|---:|---:|---:|---:|
| text: a common word | 55,075 | **2.80** | 44 | 47 |
| text: a rare word | 46 | 0.46 | **0.13** | 0.35 |
| text: two words | 17,979 | **2.06** | 15 | 27 |
| prefix: 3 letters* | 35,430 | **7.88** | 33 | 44 |
| filter genre, sort year desc | 13,867 | 0.74 | **0.34** | 1.25 |
| range of years, sort artist | 13,071 | 1.69 | **1.20** | 1.49 |
| text + drilldown (2 facets) | 55,075 | **3.38** | 113 | 91 |
| page 50, sorted on year | 100,000 | **3.24** | 3.33 | 6.42 |
| get one object by id | 1 | 0.02 | **0.01** | 0.11 |

| Writing | swindl | SQLite + FTS5 | PostgreSQL |
|---|---:|---:|---:|
| change one object, searchable at once (ms) | 19 | **0.20** | 0.78 |
| change one object, index on the timer (ms) | **1.70** | - | - |
| load, transactions of 1,000 (objects/s) | 2,477 | 13,728 | **17,186** |
| rebuild the search index (s) | 7.9 | **0.15** | 0.21 |
| on disk (MB) | 73 | **44** | 57 |
| what you run | nothing: a library | nothing: a library | a database server |

