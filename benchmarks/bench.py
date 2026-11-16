## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines swl, sil and sdbl
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "Swindl"
#
# "Swindl" is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# "Swindl" is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with "Swindl"; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
## end license ##

"""Benchmarks: swindl (sjdbl files + sil index) against SQLite with FTS5,
on the same data and the same questions.

    PYTHONPATH=. python benchmarks/bench.py            # 10,000 and 100,000 records
    PYTHONPATH=. python benchmarks/bench.py --sizes 10000 --out /tmp/results.json

The data is a record collection (vinyl): title, artist, label, genre, country, format,
year and notes, generated with a fixed seed. Words follow a Zipf distribution, so some
words are in many records and most in few, as in real titles.

Both sides are durable: swindl syncs every transaction (fsync), SQLite runs in WAL mode
with synchronous=FULL. Both answer with whole objects: swindl reads the page's objects
from their files, SQLite selects the page's rows. Timings are wall-clock, the median of
many runs after a warm-up (the file system cache is warm for both).

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


# --- the two sides ---


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


def run(size, workdir, runs):
    data = Data()
    records = [data.record() for _ in range(size)]
    results = {"size": size}
    for side_class in (SwindlSide, SqliteSide):
        path = workdir / f"{side_class.name}-{size}"
        side = side_class(path)
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
            side.store._indexes.commit()
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
        out["rebuild_seconds"] = round(time.perf_counter() - start, 2)
        out["disk"] = side.disk()
        side.close()
        print(f"  {side.name} {size}: done", file=sys.stderr)
    return results


def machine():
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
    return info


def _ms(value):
    return f"{value:.2f}" if value < 10 else f"{value:.0f}"


def _ratio(ours, theirs):
    """How many times faster swindl is (or slower, as 1/x)."""
    if ours <= theirs:
        return f"**{theirs / ours:.1f}x faster**"
    return f"{ours / theirs:.1f}x slower"


def report(results):
    """The results as Markdown tables (for benchmarks/RESULTS.md and the website)."""
    m = results["machine"]
    lines = [
        f"Measured {results['date']} on {m['cpu']}, {m['cpus']} CPUs, "
        f"{m['platform'].split('-with')[0]}; Python {m['python']}, tantivy "
        f"{m.get('tantivy', '?')}, SQLite {m['sqlite']}. Median of "
        "repeated runs, in milliseconds.",
        "",
    ]
    for run in results["runs"]:
        sw, sq = run["swindl"], run["sqlite"]
        lines += [
            f"### {run['size']:,} records",
            "",
            "| Question | hits | swindl | SQLite + FTS5 | swindl is |",
            "|---|---:|---:|---:|---|",
        ]
        for label, ours in sw["queries"].items():
            theirs = sq["queries"][label]
            lines.append(
                f"| {label} | {ours['hits']:,} | {_ms(ours['median_ms'])} | "
                f"{_ms(theirs['median_ms'])} | "
                f"{_ratio(ours['median_ms'], theirs['median_ms'])} |"
            )
        lines += [
            f"| get one object by id | 1 | {_ms(sw['get']['median_ms'])} | "
            f"{_ms(sq['get']['median_ms'])} | "
            f"{_ratio(sw['get']['median_ms'], sq['get']['median_ms'])} |",
            "",
            "| Writing | swindl | SQLite + FTS5 |",
            "|---|---:|---:|",
            f"| change one object, searchable at once (ms) | "
            f"{_ms(sw['update']['median_ms'])} | {_ms(sq['update']['median_ms'])} |",
            f"| change one object, index on the timer (ms) | "
            f"{_ms(sw['update_timer']['median_ms'])} | - |",
            f"| load, transactions of 1,000 (objects/s) | "
            f"{sw['load']['per_second']:,} | {sq['load']['per_second']:,} |",
            f"| rebuild the search index (s) | {sw['rebuild_seconds']} | "
            f"{sq['rebuild_seconds']} |",
            f"| on disk (MB) | {sw['disk']['data_bytes'] / 1e6:.0f} files + "
            f"{sw['disk']['index_bytes'] / 1e6:.0f} index | "
            f"{sq['disk']['data_bytes'] / 1e6:.0f} |",
            "",
        ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sizes", type=int, nargs="+", default=[10_000, 100_000])
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--out", type=Path, default=Path("benchmarks/results.json"))
    parser.add_argument("--workdir", type=Path, help="default: a temporary directory")
    parser.add_argument(
        "--report", type=Path, help="only print the Markdown of an earlier results file"
    )
    args = parser.parse_args()
    if args.report:
        print(report(json.loads(args.report.read_text())))
        return

    workdir = args.workdir or Path(tempfile.mkdtemp(prefix="swindl-bench-"))
    results = {"machine": machine(), "date": time.strftime("%Y-%m-%d"), "runs": []}
    try:
        for size in args.sizes:
            print(f"{size} records", file=sys.stderr)
            results["runs"].append(run(size, workdir, args.runs))
    finally:
        if not args.workdir:
            shutil.rmtree(workdir, ignore_errors=True)
    args.out.write_text(json.dumps(results, indent=2) + "\n")
    print(report(results))


if __name__ == "__main__":
    main()
