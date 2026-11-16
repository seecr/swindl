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

"""Crash safety: after a crash at any point of a transaction, the files have it
completely or not at all, and the index matches the files once the store is opened
again. Each crash is a real one: a child process that dies with os._exit."""

import subprocess
import sys
import textwrap

import pytest
from sil.indexfield import IndexField
from sjdbl.field import Field

from .base import Base
from .indexes import Commit
from .store import QueryParams, Store


class Item(Base):
    FIELDS = Base.FIELDS + [Field.str("name")]
    INDEX = Base.INDEX + [IndexField.untokenized("name")]

    def index_values(self):
        return {**super().index_values(), "name": self.name}


def run_child(tmp_path, crash_at, commit="Commit(immediate=True)"):
    """Stores a, b, c; then one transaction (a -> A, b -> B, c deleted, d new) that
    dies at crash_at: "<module path>:<attribute>" that is replaced by os._exit."""
    module_name, attribute = crash_at.split(":")
    script = textwrap.dedent(f"""
        import os, importlib
        from swindl.store.crash_test import Item
        from swindl.store import Store
        from swindl.store.indexes import Commit

        store = Store(__import__("pathlib").Path({str(tmp_path)!r}), [Item],
                      commit={commit})
        a, b, c = (Item.create(name=n) for n in "abc")
        store.put(a, b, c)
        store.commit()

        target = importlib.import_module({module_name!r})
        cls_name, _, name = {attribute!r}.rpartition(".")
        owner = getattr(target, cls_name) if cls_name else target

        def crash(*args, **kwargs):
            os._exit(3)

        setattr(owner, name, crash)
        with store.transaction():
            a.update(name="A")
            b.update(name="B")
            store.put(a, b)
            store.delete(c)
            store.put(Item.create(name="d"))
        os._exit(0)
        """)
    return subprocess.run([sys.executable, "-c", script]).returncode


def check(tmp_path):
    """The files have the transaction completely or not at all; the index matches."""
    from sjdbl import store as sjdbl_store

    sjdbl_store._opened.clear()  # a fresh start, as after a restart
    store = Store(tmp_path, [Item], commit=Commit(immediate=True))
    in_files = sorted(item.name for item in store._store.list(Item))
    assert in_files in (["a", "b", "c"], ["A", "B", "d"])
    in_index = sorted(item.name for item in store.list(Item))
    total = store.query(QueryParams(Item)).total
    assert in_index == in_files and total == len(in_files)
    for name in in_files:
        assert store.find_one(Item, name=name) is not None
    assert store._indexes.pending() == []
    assert not list((tmp_path / "store").glob("*/*.tmp"))
    store.disconnect()
    return in_files


@pytest.mark.parametrize(
    "crash_at, expected",
    [
        # sjdbl: before the commit point, at it, while renaming, while deleting
        ("sjdbl.store:Store._write_log", ["a", "b", "c"]),
        ("sjdbl.store:fsync_dir", ["A", "B", "d"]),  # right after the log's rename
        ("pathlib:Path.unlink", ["A", "B", "d"]),  # deleting c, after the renames
        # swindl: files committed, index not yet changed / changed but not committed
        ("swindl.store.store:Store._index", ["A", "B", "d"]),
        ("swindl.store.indexes:Indexes.commit", ["A", "B", "d"]),
        # before anything: the pending log
        ("swindl.store.indexes:PendingLog.add", ["a", "b", "c"]),
    ],
)
def test_crash_during_a_transaction(tmp_path, crash_at, expected):
    assert run_child(tmp_path, crash_at) == 3
    assert check(tmp_path) == expected


def test_crash_with_commit_on_search_before_a_search(tmp_path):
    """Commit on search, and no search before the crash: nothing was committed to the
    index; the pending log has the qids, so opening the store indexes them."""
    code = run_child(
        tmp_path,
        "swindl.store.indexes:Indexes.shutdown",
        commit="Commit(on_search=True, timeout=0)",
    )
    assert code == 0
    assert check(tmp_path) == ["A", "B", "d"]


def test_crash_with_the_timer_before_its_commit(tmp_path):
    """With the timer the index commits later: the pending log keeps the qids until
    then, so a crash before that commit loses nothing."""
    code = run_child(
        tmp_path, "swindl.store.indexes:Indexes.shutdown", commit="Commit(timeout=0)"
    )
    assert code == 0
    assert check(tmp_path) == ["A", "B", "d"]
