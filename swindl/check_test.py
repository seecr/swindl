## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines swl, sil and sdbl
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "Swindl"
#
# "Swindl" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

import json

from sil.indexfield import IndexField
from sjdbl.field import Field

from .check import check, main
from .store import Base
from .store.indexes import Commit
from .store.store import Store


class Shelf(Base):
    FIELDS = Base.FIELDS + [Field.str("name")]


class Book(Base):
    FIELDS = Base.FIELDS + [
        Field.str("title"),
        Field.int("year"),
        Field.reference("shelf"),
    ]
    INDEX = Base.INDEX + [
        IndexField.text("title"),
        IndexField.untokenized("code"),
        IndexField.int("year"),
    ]

    def index_values(self):
        values = super().index_values()
        values.update(title=self.title, code=self.title.lower(), year=self.year)
        return values


MODELS = [Shelf, Book]


def make(tmp_path):
    store = Store(tmp_path, MODELS, commit=Commit(immediate=True))
    shelf = store.create(Shelf, dict(name="top"))
    books = [
        store.create(Book, dict(title=t, year=y, shelf=shelf))
        for t, y in [("Dune", 1965), ("Emma", 1815)]
    ]
    return store, shelf, books


def test_all_is_well(tmp_path):
    store, _, _ = make(tmp_path)
    store.disconnect()
    assert check(tmp_path, MODELS) == []


def test_index_and_files_differ(tmp_path):
    store, shelf, (dune, emma) = make(tmp_path)
    store.disconnect()
    # behind the store's back: a file gone, a file changed, a new file
    (tmp_path / "store" / "Book" / f"{emma.id}.json").unlink()
    file = tmp_path / "store" / "Book" / f"{dune.id}.json"
    record = json.loads(file.read_text())
    record["data"]["year"] = 1966
    file.write_text(json.dumps(record))
    extra = Book.create(title="New", year=2000)
    (tmp_path / "store" / "Book" / f"{extra.id}.json").write_text(
        json.dumps(extra.to_storage())
    )
    (tmp_path / "store" / "Shelf" / f"{shelf.id}.json").unlink()

    problems = check(tmp_path, MODELS)
    assert any(f"{emma.qid} is indexed but has no file" in p for p in problems)
    assert any(f"{extra.qid} has a file but is not indexed" in p for p in problems)
    assert any(f"{dune.qid} is indexed with another year" in p for p in problems)
    assert any(f"refers to {shelf.qid}, which does not exist" in p for p in problems)
    assert any(f"{shelf.qid} is indexed but has no file" in p for p in problems)
    assert len(problems) == 5


def test_leftovers_of_a_crash(tmp_path):
    store, _, _ = make(tmp_path)
    store.disconnect()
    (tmp_path / "store" / "commit.log").write_text('{"write": [], "delete": []}')
    (tmp_path / "store" / "Book" / "x.tmp").write_text("{")
    (tmp_path / "index" / "pending.log").write_text("Book:x\n")
    (tmp_path / "store" / "Book" / "broken.json").write_text("{")
    problems = check(tmp_path, MODELS)
    assert [p.split(":")[0] for p in problems] == [
        "store/commit.log",
        "store/Book/x.tmp",
        "index/pending.log",
        f"{tmp_path}/store/Book/broken.json",
    ]


def test_main(tmp_path, capsys):
    store, _, _ = make(tmp_path)
    store.disconnect()
    assert main([str(tmp_path), "swindl.check_test:MODELS"]) == 0
    assert capsys.readouterr().out == "ok\n"
    assert main([str(tmp_path), "swindl.check_test"]) == 0
