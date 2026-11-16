"""Benchmarks: swindl (sjdbl files + sil index) against SQLite with FTS5, PostgreSQL
with its full-text search and Meilisearch, on the same data and the same questions.

    PYTHONPATH=. python benchmarks/bench.py            # 10,000 and 100,000 records
    PYTHONPATH=. python benchmarks/bench.py --sizes 10000 --out /tmp/results.json
    PYTHONPATH=. python benchmarks/bench.py --postgres "host=/tmp dbname=postgres" \
        --meilisearch http://127.0.0.1:7700 --meilisearch-key <master key>

swindl and SQLite are always measured. PostgreSQL and Meilisearch are servers: give
their address to include them (each run makes and drops its own database or index;
PostgreSQL needs psycopg, `pip install "psycopg[binary]"`).

The data is a record collection (vinyl): title, artist, label, genre, country, format,
year and notes, generated with a fixed seed. Words follow a Zipf distribution, so some
words are in many records and most in few, as in real titles.

All sides are durable: swindl syncs every transaction (fsync), SQLite runs in WAL mode
with synchronous=FULL, PostgreSQL with synchronous_commit on, and a Meilisearch write is
waited for until its task is done. All answer with whole objects and the total number of
hits. Timings are wall-clock, the median of many runs after a warm-up (caches warm).

Not part of the package."""

import argparse
import json
import platform
import random
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from sil.indexfield import IndexField
from sjdbl.field import Field

import swindl
from swindl.store import Base
from swindl.store.indexes import Commit
from swindl.store.store import QueryParams, Store

GENRES = [
    "rock", "jazz", "blues", "soul", "funk", "pop", "folk", "country", "reggae",
    "electronic", "classical", "hip hop", "punk", "metal", "disco", "gospel",
    "latin", "world", "soundtrack", "ambient",
]  # fmt: skip
COUNTRIES = ["NL", "UK", "US", "DE", "FR", "JP", "IT", "BE", "SE", "CA", "AU", "BR"]
FORMATS = ["LP", '7"', '12"', "2xLP", "EP", '10"']


class Record(Base):
    FIELDS = Base.FIELDS + [
        Field.str("title"),
        Field.str("artist"),
        Field.str("label"),
        Field.str("genre"),
        Field.str("country"),
        Field.str("format"),
        Field.int("year"),
        Field.text("notes"),
    ]
    INDEX = Base.INDEX + [
        IndexField.unqualified("all"),
        IndexField.text("title"),
        IndexField.text("artist"),
        IndexField.untokenized("artist_sort", sortable=True),
        IndexField.untokenized("genre", drilldown=True),
        IndexField.untokenized("country", drilldown=True),
        IndexField.untokenized("format"),
        IndexField.int("year", sortable=True),
    ]

    def index_values(self):
        values = super().index_values()
        values.update(
            all=f"{self.title} {self.artist} {self.label}",
            title=self.title,
            artist=self.artist,
            artist_sort=self.artist.lower(),
            genre=self.genre,
            country=self.country,
            format=self.format,
            year=self.year,
        )
        return values


# --- the data ---


def vocabulary(rng, size=3000):
    consonants, vowels = "bcdfghjklmnprstvwz", "aeiou"
    words = set()
    while len(words) < size:
        n = rng.choice([2, 2, 3, 3, 4])
        words.add(
            "".join(rng.choice(consonants) + rng.choice(vowels) for _ in range(n))
        )
    return sorted(words)


class Data:
    def __init__(self, seed=1):
        self.rng = random.Random(seed)
        self.words = vocabulary(self.rng)
        # Zipf: word n is used about 1/n as often as the first
        self.weights = [1 / (n + 1) for n in range(len(self.words))]
        self.artists = [self.phrase(1, 3).title() for _ in range(5000)]
        self.labels = [self.phrase(1, 2).title() + " Records" for _ in range(400)]

    def phrase(self, low, high):
        n = self.rng.randint(low, high)
        return " ".join(self.rng.choices(self.words, self.weights, k=n))

    def record(self):
        return dict(
            title=self.phrase(1, 5).capitalize(),
            artist=self.rng.choice(self.artists),
            label=self.rng.choice(self.labels),
            genre=self.rng.choices(GENRES, [1 / (n + 1) for n in range(20)])[0],
            country=self.rng.choice(COUNTRIES),
            format=self.rng.choice(FORMATS),
            year=self.rng.randint(1950, 2025),
            notes=self.phrase(5, 30),
        )


# --- timing ---


def timed(fn, runs, warmup=3):
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000)
    times.sort()
    return {
        "median_ms": round(statistics.median(times), 3),
        "p95_ms": round(times[int(len(times) * 0.95) - 1], 3),
    }


def du(path):
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


# --- the sides ---


class SwindlSide:
    name = "swindl"

    def __init__(self, path):
        self.path = path
        self.store = Store(path, [Record], commit=Commit(immediate=True))
        self.qids = []

    def load(self, records, per_transaction=1000):
        for start in range(0, len(records), per_transaction):
            with self.store.transaction():
                for values in records[start : start + per_transaction]:
                    obj = Record.create(**values)
                    self.store.put(obj)
                    self.qids.append(obj.qid)

    def get(self, qid):
        return self.store.get(qid)

    def update(self, qid, title):
        obj = self.store.get(qid)
        obj.update(title=title)
        self.store.put(obj)

    def text_query(self, words):
        r = self.store.query(QueryParams(Record, query=words, size=20))
        return r.total, r.objs

    def prefix_query(self, prefix):
        r = self.store.query(QueryParams(Record, query=f"{prefix}*", size=20))
        return r.total, r.objs

    def filter_sorted(self, genre):
        r = self.store.query(
            QueryParams(
                Record,
                filters={"genre": genre},
                sort=[{"field": "year", "reverse": True}],
                size=20,
            )
        )
        return r.total, r.objs

    def range_sorted(self, low, high):
        r = self.store.query(
            QueryParams(Record, query=f"year:[{low} TO {high}]", sort="artist_sort")
        )
        return r.total, r.objs

    def facets(self, words):
        r = self.store.query(
            QueryParams(
                Record,
                query=words,
                size=20,
                drilldown=[{"name": "genre"}, {"name": "country"}],
            )
        )
        return r.total, r.objs, r.drilldown

    def deep_page(self, page):
        r = self.store.query(QueryParams(Record, sort="year", page=page, size=20))
        return r.total, r.objs

    def rebuild(self):
        self.store.reindex([Record])

    def disk(self):
        return {
            "data_bytes": du(self.path / "store"),
            "index_bytes": du(self.path / "index"),
        }

    def close(self):
        self.store.disconnect()


class SqliteSide:
    name = "sqlite"
    COLUMNS = "id, rev, title, artist, label, genre, country, format, year, notes"

    def __init__(self, path):
        self.path = path
        path.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path / "records.db", check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE records (
                id TEXT UNIQUE NOT NULL, rev TEXT, title TEXT, artist TEXT,
                label TEXT, genre TEXT, country TEXT, format TEXT, year INTEGER,
                notes TEXT);
            CREATE INDEX records_genre_year ON records (genre, year);
            CREATE INDEX records_year_artist ON records (year, artist COLLATE NOCASE);
            CREATE INDEX records_artist ON records (artist COLLATE NOCASE);
            CREATE VIRTUAL TABLE records_fts USING fts5(
                title, artist, label, content='records', content_rowid='rowid');
            CREATE TRIGGER records_ai AFTER INSERT ON records BEGIN
                INSERT INTO records_fts(rowid, title, artist, label)
                VALUES (new.rowid, new.title, new.artist, new.label);
            END;
            CREATE TRIGGER records_au AFTER UPDATE ON records BEGIN
                INSERT INTO records_fts(records_fts, rowid, title, artist, label)
                VALUES ('delete', old.rowid, old.title, old.artist, old.label);
                INSERT INTO records_fts(rowid, title, artist, label)
                VALUES (new.rowid, new.title, new.artist, new.label);
            END;
            """)
        self.qids = []

    def load(self, records, per_transaction=1000):
        for start in range(0, len(records), per_transaction):
            rows = []
            for values in records[start : start + per_transaction]:
                id = str(uuid.uuid4())
                rows.append((id, str(uuid.uuid4()), *(values[k] for k in (
                    "title", "artist", "label", "genre", "country", "format",
                    "year", "notes"))))  # fmt: skip
                self.qids.append(id)
            with self.db:
                self.db.executemany(
                    f"INSERT INTO records ({self.COLUMNS}) VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )

    def _objs(self, cursor):
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    def get(self, id):
        return self._objs(
            self.db.execute(f"SELECT {self.COLUMNS} FROM records WHERE id = ?", (id,))
        )[0]

    def update(self, id, title):
        with self.db:
            # a revision check, as swindl does
            rev = self.db.execute("SELECT rev FROM records WHERE id = ?", (id,))
            old = rev.fetchone()[0]
            self.db.execute(
                "UPDATE records SET title = ?, rev = ? WHERE id = ? AND rev = ?",
                (title, str(uuid.uuid4()), id, old),
            )

    def _fts(self, match):
        total = self.db.execute(
            "SELECT count(*) FROM records_fts WHERE records_fts MATCH ?", (match,)
        ).fetchone()[0]
        objs = self._objs(
            self.db.execute(
                f"SELECT {', '.join('r.' + c.strip() for c in self.COLUMNS.split(','))}"
                " FROM records_fts f JOIN records r ON r.rowid = f.rowid"
                " WHERE records_fts MATCH ? ORDER BY f.rank LIMIT 20",
                (match,),
            )
        )
        return total, objs

    def text_query(self, words):
        return self._fts(" OR ".join(words.split()))

    def prefix_query(self, prefix):
        return self._fts(f"{prefix}*")

    def filter_sorted(self, genre):
        total = self.db.execute(
            "SELECT count(*) FROM records WHERE genre = ?", (genre,)
        ).fetchone()[0]
        objs = self._objs(
            self.db.execute(
                f"SELECT {self.COLUMNS} FROM records WHERE genre = ? "
                "ORDER BY year DESC LIMIT 20",
                (genre,),
            )
        )
        return total, objs

    def range_sorted(self, low, high):
        total = self.db.execute(
            "SELECT count(*) FROM records WHERE year BETWEEN ? AND ?", (low, high)
        ).fetchone()[0]
        objs = self._objs(
            self.db.execute(
                f"SELECT {self.COLUMNS} FROM records WHERE year BETWEEN ? AND ? "
                "ORDER BY artist COLLATE NOCASE LIMIT 20",
                (low, high),
            )
        )
        return total, objs

    def facets(self, words):
        match = " OR ".join(words.split())
        total, objs = self._fts(match)
        drilldown = {}
        for column in ("genre", "country"):
            drilldown[column] = self.db.execute(
                f"SELECT {column}, count(*) AS n FROM records WHERE rowid IN "
                "(SELECT rowid FROM records_fts WHERE records_fts MATCH ?) "
                f"GROUP BY {column} ORDER BY n DESC, {column} LIMIT 10",
                (match,),
            ).fetchall()
        return total, objs, drilldown

    def deep_page(self, page):
        total = self.db.execute("SELECT count(*) FROM records").fetchone()[0]
        objs = self._objs(
            self.db.execute(
                f"SELECT {self.COLUMNS} FROM records ORDER BY year, rowid "
                "LIMIT 20 OFFSET ?",
                (page * 20,),
            )
        )
        return total, objs

    def rebuild(self):
        with self.db:
            self.db.execute("INSERT INTO records_fts(records_fts) VALUES ('rebuild')")

    def disk(self):
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return {"data_bytes": du(self.path), "index_bytes": None}

    def close(self):
        self.db.close()


class PostgresSide:
    """PostgreSQL with its full-text search: a tsvector column (generated, so always
    up to date) with a GIN index, and B-tree indexes for the filters and sorts.
    Durable: synchronous_commit on (the default)."""

    name = "postgres"
    COLUMNS = SqliteSide.COLUMNS

    def __init__(self, dsn, size):
        import psycopg

        self.db_name = f"swindl_bench_{size}"
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {self.db_name}")
            admin.execute(f"CREATE DATABASE {self.db_name}")
        self.dsn = psycopg.conninfo.make_conninfo(dsn, dbname=self.db_name)
        # autocommit: every statement is its own transaction, unless in transaction()
        self.db = psycopg.connect(self.dsn, autocommit=True)
        # psycopg prepares a statement after 5 runs, and PostgreSQL may then switch to
        # a generic plan: made for a common word, it scans everything for a rare one
        # (4 ms instead of 0.3). A plan per query, as an application would want.
        self.db.execute("SET plan_cache_mode = force_custom_plan")
        self.db.execute("""
                CREATE TABLE records (
                    id TEXT PRIMARY KEY, rev TEXT, title TEXT, artist TEXT,
                    label TEXT, genre TEXT, country TEXT, format TEXT,
                    year INTEGER, notes TEXT,
                    tsv tsvector GENERATED ALWAYS AS (
                        to_tsvector('simple', title || ' ' || artist || ' ' || label)
                    ) STORED);
                CREATE INDEX records_tsv ON records USING GIN (tsv);
                CREATE INDEX records_genre_year ON records (genre, year);
                CREATE INDEX records_year_artist ON records (year, lower(artist));
                CREATE INDEX records_artist ON records (lower(artist));
                """)
        self.qids = []

    def load(self, records, per_transaction=1000):
        for start in range(0, len(records), per_transaction):
            rows = []
            for values in records[start : start + per_transaction]:
                id = str(uuid.uuid4())
                rows.append((id, str(uuid.uuid4()), *(values[k] for k in (
                    "title", "artist", "label", "genre", "country", "format",
                    "year", "notes"))))  # fmt: skip
                self.qids.append(id)
            with self.db.transaction(), self.db.cursor() as cursor:
                cursor.executemany(
                    f"INSERT INTO records ({self.COLUMNS}) VALUES "
                    "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    rows,
                )
        # as after any bulk load: VACUUM also moves the GIN index's pending entries
        # into the index proper (until then a rare word took 4 ms instead of 0.4)
        self.db.execute("VACUUM ANALYZE records")

    def _objs(self, sql, params):
        with self.db.cursor() as cursor:
            cursor.execute(sql, params)
            names = [d.name for d in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]

    def _one(self, sql, params):
        return self.db.execute(sql, params).fetchone()[0]

    def get(self, id):
        return self._objs(f"SELECT {self.COLUMNS} FROM records WHERE id = %s", (id,))[0]

    def update(self, id, title):
        with self.db.transaction():
            old = self.db.execute(
                "SELECT rev FROM records WHERE id = %s", (id,)
            ).fetchone()[0]
            self.db.execute(
                "UPDATE records SET title = %s, rev = %s WHERE id = %s AND rev = %s",
                (title, str(uuid.uuid4()), id, old),
            )

    def _fts(self, tsquery):
        where = "tsv @@ to_tsquery('simple', %s)"
        total = self._one(f"SELECT count(*) FROM records WHERE {where}", (tsquery,))
        objs = self._objs(
            f"SELECT {self.COLUMNS} FROM records WHERE {where} "
            "ORDER BY ts_rank(tsv, to_tsquery('simple', %s)) DESC LIMIT 20",
            (tsquery, tsquery),
        )
        return total, objs

    def text_query(self, words):
        return self._fts(" | ".join(words.split()))

    def prefix_query(self, prefix):
        return self._fts(f"{prefix}:*")

    def filter_sorted(self, genre):
        total = self._one("SELECT count(*) FROM records WHERE genre = %s", (genre,))
        objs = self._objs(
            f"SELECT {self.COLUMNS} FROM records WHERE genre = %s "
            "ORDER BY year DESC LIMIT 20",
            (genre,),
        )
        return total, objs

    def range_sorted(self, low, high):
        total = self._one(
            "SELECT count(*) FROM records WHERE year BETWEEN %s AND %s", (low, high)
        )
        objs = self._objs(
            f"SELECT {self.COLUMNS} FROM records WHERE year BETWEEN %s AND %s "
            "ORDER BY lower(artist) LIMIT 20",
            (low, high),
        )
        return total, objs

    def facets(self, words):
        tsquery = " | ".join(words.split())
        total, objs = self._fts(tsquery)
        drilldown = {}
        for column in ("genre", "country"):
            with self.db.cursor() as cursor:
                cursor.execute(
                    f"SELECT {column}, count(*) AS n FROM records "
                    "WHERE tsv @@ to_tsquery('simple', %s) "
                    f"GROUP BY {column} ORDER BY n DESC, {column} LIMIT 10",
                    (tsquery,),
                )
                drilldown[column] = cursor.fetchall()
        return total, objs, drilldown

    def deep_page(self, page):
        total = self._one("SELECT count(*) FROM records", ())
        objs = self._objs(
            f"SELECT {self.COLUMNS} FROM records ORDER BY year, id "
            "LIMIT 20 OFFSET %s",
            (page * 20,),
        )
        return total, objs

    def rebuild(self):
        self.db.execute("REINDEX INDEX records_tsv")

    def disk(self):
        return {
            "data_bytes": self._one("SELECT pg_total_relation_size('records')", ()),
            "index_bytes": None,
        }

    def close(self):
        self.db.close()


class MeilisearchSide:
    """Meilisearch, a search server: the records as documents, with filters, sorts
    and facets declared. Typo tolerance is off, so it finds what the others find.
    Every write waits until its task is done, so it is searchable (and stored) when
    it returns. Through its HTTP API, with the standard library only."""

    name = "meilisearch"

    def __init__(self, url, key, size):
        self.url, self.key = url.rstrip("/"), key
        self.index = f"swindl_bench_{size}"
        self._request("DELETE", f"/indexes/{self.index}", wait=True, missing_ok=True)
        self._request(
            "POST", "/indexes", {"uid": self.index, "primaryKey": "id"}, wait=True
        )
        self._request(
            "PATCH",
            f"/indexes/{self.index}/settings",
            {
                "searchableAttributes": ["title", "artist", "label"],
                "filterableAttributes": ["genre", "country", "year"],
                "sortableAttributes": ["year", "artist_sort"],
                "typoTolerance": {"enabled": False},
                "pagination": {"maxTotalHits": 1_000_000},
                "faceting": {"maxValuesPerFacet": 100},
            },
            wait=True,
        )
        self.qids = []

    def _request(self, method, path, body=None, wait=False, missing_ok=False):
        import urllib.error
        import urllib.request

        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.url + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if self.key:
            request.add_header("Authorization", f"Bearer {self.key}")
        try:
            with urllib.request.urlopen(request) as response:
                answer = json.loads(response.read() or b"null")
        except urllib.error.HTTPError as e:
            if missing_ok and e.code == 404:
                return None
            raise RuntimeError(f"{method} {path}: {e.code} {e.read()[:300]}") from e
        if wait and answer and "taskUid" in answer:
            self._wait(answer["taskUid"], missing_ok)
        return answer

    def _wait(self, task, missing_ok=False):
        while True:
            state = self._request("GET", f"/tasks/{task}")
            if state["status"] == "succeeded":
                return
            error = state.get("error") or {}
            if missing_ok and error.get("code") == "index_not_found":
                return  # deleting what isn't there: the task fails, which is fine
            if state["status"] in ("failed", "canceled"):
                raise RuntimeError(f"task {task}: {error}")
            time.sleep(0.0005)

    def _doc(self, id, rev, values):
        return {"id": id, "rev": rev, "artist_sort": values["artist"].lower(),
                **values}  # fmt: skip

    def load(self, records, per_transaction=1000):
        for start in range(0, len(records), per_transaction):
            docs = []
            for values in records[start : start + per_transaction]:
                id = uuid.uuid4().hex
                docs.append(self._doc(id, uuid.uuid4().hex, values))
                self.qids.append(id)
            self._request("POST", f"/indexes/{self.index}/documents", docs, wait=True)

    def get(self, id):
        return self._request("GET", f"/indexes/{self.index}/documents/{id}")

    def update(self, id, title):
        # no revisions in Meilisearch: a partial update, waited for
        self._request(
            "PUT",
            f"/indexes/{self.index}/documents",
            [{"id": id, "title": title}],
            wait=True,
        )

    def _search(self, **body):
        answer = self._request("POST", f"/indexes/{self.index}/search",
                               {"limit": 20, **body})  # fmt: skip
        return answer

    def text_query(self, words):
        r = self._search(q=words, matchingStrategy="last")
        return r["estimatedTotalHits"], r["hits"]

    def prefix_query(self, prefix):
        r = self._search(q=prefix)  # the last word is a prefix in Meilisearch
        return r["estimatedTotalHits"], r["hits"]

    def filter_sorted(self, genre):
        r = self._search(filter=f'genre = "{genre}"', sort=["year:desc"])
        return r["estimatedTotalHits"], r["hits"]

    def range_sorted(self, low, high):
        r = self._search(filter=f"year {low} TO {high}", sort=["artist_sort:asc"])
        return r["estimatedTotalHits"], r["hits"]

    def facets(self, words):
        r = self._search(q=words, facets=["genre", "country"])
        return r["estimatedTotalHits"], r["hits"], r["facetDistribution"]

    def deep_page(self, page):
        r = self._search(sort=["year:asc"], offset=page * 20)
        return r["estimatedTotalHits"], r["hits"]

    def rebuild(self):
        pass  # no equivalent: Meilisearch is the index

    def disk(self):
        stats = self._request("GET", "/stats")
        return {"data_bytes": stats.get("databaseSize"), "index_bytes": None}

    def close(self):
        self._request("DELETE", f"/indexes/{self.index}", wait=True)


# --- the run ---


def questions(data):
    common = data.words[0]
    rare = data.words[1500]
    two = f"{data.words[3]} {data.words[40]}"
    prefix = data.words[2][:3]
    return {
        "text: a common word": ("text_query", (common,)),
        "text: a rare word": ("text_query", (rare,)),
        "text: two words": ("text_query", (two,)),
        "prefix: 3 letters*": ("prefix_query", (prefix,)),
        "filter genre, sort year desc": ("filter_sorted", ("jazz",)),
        "range of years, sort artist": ("range_sorted", (1970, 1979)),
        "text + drilldown (2 facets)": ("facets", (common,)),
        "page 50, sorted on year": ("deep_page", (50,)),
    }


def run(size, workdir, runs, postgres=None, meilisearch=None, meilisearch_key=None):
    data = Data()
    records = [data.record() for _ in range(size)]
    results = {"size": size}
    makers = [
        lambda: SwindlSide(workdir / f"swindl-{size}"),
        lambda: SqliteSide(workdir / f"sqlite-{size}"),
    ]
    if postgres:
        makers.append(lambda: PostgresSide(postgres, size))
    if meilisearch:
        makers.append(lambda: MeilisearchSide(meilisearch, meilisearch_key, size))
    for make in makers:
        side = make()
        out = results.setdefault(side.name, {})

        start = time.perf_counter()
        side.load(records)
        seconds = time.perf_counter() - start
        out["load"] = {
            "seconds": round(seconds, 2),
            "per_second": round(size / seconds),
        }

        rng = random.Random(2)
        sample = rng.sample(side.qids, min(1000, size))
        out["get"] = timed(lambda: side.get(rng.choice(sample)), runs * 5)
        counter = iter(range(10**9))
        out["update"] = timed(
            lambda: side.update(rng.choice(sample), f"changed {next(counter)}"), runs
        )
        if side.name == "swindl":
            # the default Commit(): the files are synced at once, the index commits on
            # the timer (here: right after the measurement)
            side.store._indexes._immediate = False
            out["update_timer"] = timed(
                lambda: side.update(rng.choice(sample), f"changed {next(counter)}"),
                runs,
            )
            side.store.commit()
            side.store._indexes._immediate = True

        out["queries"] = {}
        for label, (method, args) in questions(data).items():
            answer = getattr(side, method)(*args)
            out["queries"][label] = {
                **timed(lambda: getattr(side, method)(*args), runs),
                "hits": answer[0],
            }

        start = time.perf_counter()
        side.rebuild()
        out["rebuild_seconds"] = (
            None
            if side.name == "meilisearch"
            else round(time.perf_counter() - start, 2)
        )
        out["disk"] = side.disk()
        side.close()
        print(f"  {side.name} {size}: done", file=sys.stderr)
    return results


def machine(postgres=None, meilisearch=None, meilisearch_key=None):
    info = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpus": __import__("os").cpu_count(),
        "sqlite": sqlite3.sqlite_version,
        "swindl": swindl.__version__ if hasattr(swindl, "__version__") else "",
    }
    try:
        info["cpu"] = next(
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().split("\n")
            if line.startswith("model name")
        )
    except (OSError, StopIteration):
        info["cpu"] = platform.processor()
    try:
        info["tantivy"] = (
            subprocess.run(
                [sys.executable, "-m", "pip", "show", "tantivy"],
                capture_output=True,
                text=True,
            )
            .stdout.split("Version: ")[1]
            .split()[0]
        )
    except IndexError:
        pass
    if postgres:
        import psycopg

        with psycopg.connect(postgres) as db:
            info["postgres"] = (
                db.execute("SHOW server_version").fetchone()[0].split()[0]
            )
    if meilisearch:
        side = MeilisearchSide.__new__(MeilisearchSide)
        side.url, side.key = meilisearch.rstrip("/"), meilisearch_key
        info["meilisearch"] = side._request("GET", "/version")["pkgVersion"]
    return info


def _ms(value):
    return f"{value:.2f}" if value < 10 else f"{value:.0f}"


SIDES = {
    "swindl": ("swindl", "nothing: a library"),
    "sqlite": ("SQLite + FTS5", "nothing: a library"),
    "postgres": ("PostgreSQL", "a database server"),
    "meilisearch": ("Meilisearch", "a search server, and a store for the data"),
}


def report(results):
    """The results as Markdown tables (for benchmarks/RESULTS.md and the website):
    one column per side, the fastest in bold."""
    m = results["machine"]
    versions = ", ".join(
        f"{name} {m[key]}"
        for name, key in [("Python", "python"), ("tantivy", "tantivy"),
                          ("SQLite", "sqlite"), ("PostgreSQL", "postgres"),
                          ("Meilisearch", "meilisearch")]  # fmt: skip
        if m.get(key)
    )
    lines = [
        f"Measured {results['date']} on {m['cpu']}, {m['cpus']} CPUs, "
        f"{m['platform'].split('-with')[0]}; {versions}. Median of repeated runs, "
        "in milliseconds; the fastest in bold.",
        "",
    ]
    for run in results["runs"]:
        sides = [name for name in SIDES if name in run]
        head = " | ".join(SIDES[name][0] for name in sides)

        def row(label, values, fmt=_ms, best=min):
            known = [v for v in values if v is not None]
            winner = best(known) if known else None
            cells = [
                "-" if v is None else (f"**{fmt(v)}**" if v == winner else fmt(v))
                for v in values
            ]
            return f"| {label} | " + " | ".join(cells) + " |"

        lines += [
            f"### {run['size']:,} records",
            "",
            f"| Question | hits | {head} |",
            "|---|---:|" + "---:|" * len(sides),
        ]
        for label, ours in run["swindl"]["queries"].items():
            values = [run[name]["queries"][label]["median_ms"] for name in sides]
            lines.append(
                row(f"{label}", values).replace(
                    f"| {label} |", f"| {label} | {ours['hits']:,} |", 1
                )
            )
        lines.append(
            row(
                "get one object by id", [run[n]["get"]["median_ms"] for n in sides]
            ).replace("| get one object by id |", "| get one object by id | 1 |", 1)
        )
        lines += ["", f"| Writing | {head} |", "|---|" + "---:|" * len(sides)]
        lines.append(row("change one object, searchable at once (ms)",
                         [run[n]["update"]["median_ms"] for n in sides]))  # fmt: skip
        lines.append(row(
            "change one object, index on the timer (ms)",
            [run[n].get("update_timer", {}).get("median_ms") for n in sides],
        ))  # fmt: skip
        lines.append(row(
            "load, transactions of 1,000 (objects/s)",
            [run[n]["load"]["per_second"] for n in sides],
            fmt=lambda v: f"{v:,}", best=max,
        ))  # fmt: skip
        lines.append(row(
            "rebuild the search index (s)",
            [run[n]["rebuild_seconds"] for n in sides], fmt=str,
        ))  # fmt: skip
        lines.append(row(
            "on disk (MB)",
            [_disk(run[n]["disk"]) for n in sides], fmt=lambda v: f"{v:.0f}",
        ))  # fmt: skip
        lines.append(
            "| what you run | " + " | ".join(SIDES[n][1] for n in sides) + " |"
        )
        lines.append("")
    return "\n".join(lines)


def _disk(disk):
    if disk.get("data_bytes") is None:
        return None
    return (disk["data_bytes"] + (disk.get("index_bytes") or 0)) / 1e6


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sizes", type=int, nargs="+", default=[10_000, 100_000])
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--out", type=Path, default=Path("benchmarks/results.json"))
    parser.add_argument("--workdir", type=Path, help="default: a temporary directory")
    parser.add_argument(
        "--report", type=Path, help="only print the Markdown of an earlier results file"
    )
    parser.add_argument("--postgres", help="a PostgreSQL connection string (libpq)")
    parser.add_argument("--meilisearch", help="the url of a Meilisearch server")
    parser.add_argument("--meilisearch-key", help="its master key, if it has one")
    args = parser.parse_args()
    if args.report:
        print(report(json.loads(args.report.read_text())))
        return

    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="swindl-bench-"))
    results = {
        "machine": machine(args.postgres, args.meilisearch, args.meilisearch_key),
        "date": time.strftime("%Y-%m-%d"),
        "runs": [],
    }
    try:
        for size in args.sizes:
            print(f"{size} records", file=sys.stderr)
            results["runs"].append(
                run(size, workdir, args.runs, args.postgres, args.meilisearch,
                    args.meilisearch_key)  # fmt: skip
            )
    finally:
        if not args.workdir:
            shutil.rmtree(workdir, ignore_errors=True)
    args.out.write_text(json.dumps(results, indent=2) + "\n")
    print(report(results))


if __name__ == "__main__":
    main()
