## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines sjdbl's files and sil's index
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "swindl"
#
# "swindl" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

import pytest
from sil.indexfield import IndexField
from sjdbl.base import Proxy
from sjdbl.field import Field

from .base import Base
from .indexes import Commit
from .store import HasChangedException, QueryParams, Store


class Person(Base):
    FIELDS = Base.FIELDS + [
        Field.str("name"),
        Field.date("dob"),
        Field.reference("parent"),
    ]


def test_add_get_list_delete(tmp_path):
    recordstore = Store(tmp_path, [Person], commit=Commit(immediate=True))

    p = Person()
    recordstore.put(p)

    p_again = recordstore.get(p.qid)

    assert p_again.qid == p.qid

    persons = list(recordstore.list(Person))
    assert len(persons) == 1
    assert persons[0].qid == p.qid

    recordstore.delete(p)
    p_again = recordstore.get(p.qid)
    assert p_again is None

    persons = list(recordstore.list(Person))
    assert len(persons) == 0


def test_delete_a_reference_or_a_qid(tmp_path):
    """A Proxy (as references and collections give) or a qid deletes as the object:
    from the files and the index, without loading it."""
    store = Store(tmp_path, [Person], commit=Commit(immediate=True))
    by_proxy, by_qid, gone = [Person() for _ in range(3)]
    for p in (by_proxy, by_qid, gone):
        store.put(p)
    store.delete(Proxy(store, by_proxy.qid))
    store.delete(by_qid.qid)
    assert store.get(by_proxy.qid) is None and store.get(by_qid.qid) is None
    assert [p.qid for p in store.list(Person)] == [gone.qid]
    store.delete(gone)
    store.delete(Proxy(store, gone.qid))  # already gone: nothing to load, no error
    assert list(store.list(Person)) == []


def test_list(tmp_path):
    recordstore = Store(tmp_path, [Person], commit=Commit(immediate=True))

    for i in range(100):
        p = Person()
        recordstore.put(p)

    persons = list(recordstore.list(Person))
    assert len(persons) == 100


def test_has_changed_exception_on_get(tmp_path):
    class Book(Base):
        FIELDS = Base.FIELDS + [Field.str("title")]

    store = Store(tmp_path, [Book], commit=Commit(immediate=True))

    book = Book.create(title="Lord of the rings")
    store.put(book)

    book_revisited = store.get(book.qid)
    book_revisited.update(title="Lady of the rings")
    store.put(book_revisited)

    with pytest.raises(HasChangedException):
        store.get(book.qrid)


def test_archive(tmp_path):
    class Book(Base):
        FIELDS = Base.FIELDS + [Field.str("title")]

    store = Store(tmp_path, [Book], commit=Commit(immediate=True))

    book1 = Book.create(title="Lord of the rings")
    store.put(book1)
    book2 = Book.create(title="The hobbit")
    store.put(book2)

    assert list(store.list(Book)) == [book1, book2]

    store.archive(book1)
    assert list(store.list(Book)) == [book2]

    assert list(store.list(Book, include_archived=True)) == [book2, book1]

    assert store.get(book1.qid) is None
    assert store.get(book1.qid, include_archived=True) == book1


def test_put_with_only_unindexed_changes(tmp_path):
    class Note(Base):
        FIELDS = Base.FIELDS + [Field.str("key"), Field.str("seen")]
        INDEX = Base.INDEX + [IndexField.untokenized("key")]

        def index_values(self):
            values = super().index_values()
            values["key"] = self.key
            return values

    store = Store(tmp_path, [Note], commit=Commit(immediate=True))
    note = store.create(Note, values={"key": "a", "seen": "1"})
    for seen in ["2", "3"]:  # not indexed: only the store changes
        note.update(seen=seen)
        store.put(note)
    assert store.get(note.qid).seen == "3"
    only_a = {"key": "a", "__archived__": "False"}
    found = store.query(QueryParams("Note", filters=only_a))
    assert found.total == 1 and found.objs[0].seen == "3"

    store.archive(note)  # an indexed value changes: the index follows
    found = store.query(QueryParams("Note", filters=only_a))
    assert found.total == 0


class _Commits:
    """A commit target that counts the commits of an index."""

    def __init__(self):
        self.count = 0

    def commit(self):
        self.count += 1


class Pet(Base):
    FIELDS = Base.FIELDS + [Field.str("name")]


def _counted(store, cls):
    commits = _Commits()
    store._indexes.get(cls)._commit.add_target(commits)
    return commits


def test_a_transaction_commits_once_per_index_at_the_end(tmp_path):
    store = Store(tmp_path, [Person, Pet], commit=Commit(immediate=True))
    persons, pets = _counted(store, Person), _counted(store, Pet)
    with store.transaction():
        people = [store.create(Person, values={"name": f"p{nr}"}) for nr in range(5)]
        store.create(Pet, values={"name": "Rex"})
        assert (persons.count, pets.count) == (0, 0)
        assert list(store.list(Person)) == []  # the index: not yet
        assert store.get(people[0].qid).name == "p0"  # this thread sees its puts
    assert (persons.count, pets.count) == (1, 1)
    assert len(list(store.list(Person))) == 5

    with store.transaction():  # nested: the outermost commits
        with store.transaction():
            store.create(Person, values={"name": "p5"})
        store.create(Person, values={"name": "p6"})
        assert persons.count == 1
    assert (persons.count, pets.count) == (2, 1)

    with store.transaction():  # nothing indexed changed: no commit
        store.put(people[0])
    assert persons.count == 2

    store.create(Person, values={"name": "p7"})  # a put alone: its own transaction
    assert persons.count == 3


def test_an_exception_discards_the_transaction(tmp_path):
    store = Store(tmp_path, [Person], commit=Commit(immediate=True))
    persons = _counted(store, Person)
    kept = store.create(Person, values={"name": "kept"})
    rev = kept["__rev__"]
    with pytest.raises(ValueError):
        with store.transaction():
            store.delete(kept)
            kept_again = store.create(Person, values={"name": "new"})
            assert store.get(kept.qid) is None
            raise ValueError("oops")
    assert persons.count == 1
    assert [p.name for p in store.list(Person)] == ["kept"]
    assert store.get(kept.qid).name == "kept" and store.get(kept_again.qid) is None
    assert kept["__rev__"] == rev
    assert store._indexes.pending() == []


def test_a_delete_is_searchable_at_once_also_with_the_timer(tmp_path):
    store = Store(tmp_path, [Person], commit=Commit(timeout=0))
    person = store.create(Person, values={"name": "p"})
    assert list(store.list(Person)) == []  # not committed: no timer
    store.commit()
    assert len(list(store.list(Person))) == 1
    store.delete(person)
    assert list(store.query(QueryParams(Person)).objs) == []
    assert store.query(QueryParams(Person)).total == 0


class Counter(Base):
    FIELDS = Base.FIELDS + [Field.str("name"), Field.int("count")]
    INDEX = [IndexField.untokenized(name="name"), IndexField.untokenized(name="count")]

    def index_values(self):
        return {"name": self.name, "count": str(self.count)}


def test_threads_saving_the_same_objects(tmp_path):
    """Many threads change the same objects at once (as plain def endpoints do from
    Starlette's thread pool): no exception other than a conflict, and afterwards the
    index has the values in the files."""
    from concurrent.futures import ThreadPoolExecutor

    store = Store(tmp_path, [Counter], commit=Commit(immediate=True))
    counters = [Counter.create(name=f"c{n}") for n in range(5)]
    for counter in counters:
        store.put(counter)

    def bump(n):
        qid = counters[n % 5].qid
        while True:
            counter = store.get(qid)
            counter.update(count=counter.count + 1)
            try:
                store.put(counter)
                return
            except Exception as e:  # sjdbl's HasChangedException: load again
                assert type(e).__name__ == "HasChangedException"

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(bump, range(200)))

    for counter in counters:
        on_disk = store.get(counter.qid)
        assert on_disk.count == 40
        found = store.find_one(Counter, name=on_disk.name, count=str(on_disk.count))
        assert found is not None and found.qid == counter.qid


def test_a_hit_without_a_file_is_skipped(tmp_path):
    """An id in the index whose file is gone (a crash between the file delete and the
    index delete) gives no None among the results."""
    store = Store(tmp_path, [Counter], commit=Commit(immediate=True))
    kept, gone = Counter.create(name="kept"), Counter.create(name="gone")
    store.put(kept, gone)
    (tmp_path / "store" / "Counter" / f"{gone.id}.json").unlink()

    result = store.query(QueryParams(Counter))
    assert [obj.qid for obj in result.objs] == [kept.qid]
    assert [obj.qid for obj in store.list(Counter)] == [kept.qid]
    assert store.find_by_field(Counter, "name", "gone") == []


def test_the_index_gets_the_last_saved_values(tmp_path, monkeypatch):
    """Thread A saves the file and is slow to index; thread B saves a newer version
    meanwhile. The index must end with B's values, not A's."""
    import threading

    store = Store(tmp_path, [Counter], commit=Commit(immediate=True))
    counter = Counter.create(name="c")
    store.put(counter)
    b_done = threading.Event()
    add_record = store._indexes.add_record

    def slow_add_record(obj):
        if obj.count == 1:  # A: wait (at most a moment) for B to have saved
            b_done.wait(timeout=0.5)
        add_record(obj)

    monkeypatch.setattr(store._indexes, "add_record", slow_add_record)

    def a():
        obj = store.get(counter.qid)
        obj.update(count=1)
        store.put(obj)

    thread_a = threading.Thread(target=a)
    thread_a.start()
    while store.get(counter.qid).count != 1:  # A's file is written
        pass

    def b():
        obj = store.get(counter.qid)
        obj.update(count=2)
        store.put(obj)
        b_done.set()

    thread_b = threading.Thread(target=b)
    thread_b.start()
    thread_a.join()
    thread_b.join()

    assert store.get(counter.qid).count == 2
    assert store.find_one(Counter, count="2") is not None
    assert store.find_one(Counter, count="1") is None


async def test_the_timer_commits_and_empties_the_pending_log(tmp_path):
    import asyncio

    store = Store(tmp_path, [Person], commit=Commit(timeout=0.05))
    store.create(Person, values={"name": "p"})
    assert store._indexes.pending() != []
    for _ in range(100):
        await asyncio.sleep(0.02)
        if store._indexes.pending() == []:
            break
    assert len(list(store.list(Person))) == 1
    assert store._indexes.pending() == []
    store.disconnect()


def test_commit_on_search(tmp_path):
    """Commit(on_search=True): saving commits nothing; the next search commits once
    (for all the saves before it) and finds them; a search without changes commits
    nothing."""
    store = Store(tmp_path, [Person], commit=Commit(on_search=True, timeout=0))
    persons = _counted(store, Person)
    people = [store.create(Person, values={"name": f"p{nr}"}) for nr in range(5)]
    assert persons.count == 0
    assert len(list(store.list(Person))) == 5  # the search commits first
    assert persons.count == 1
    assert len(list(store.list(Person))) == 5
    assert store.find_one(Person, __id__=people[0].id) is not None
    assert persons.count == 1  # nothing changed: no commit
    assert store._indexes.pending() == []

    store.delete(people[0])  # a delete waits for the next search too
    assert persons.count == 1
    assert len(list(store.list(Person))) == 4
    assert store.find_by_field(Person, "__id__", people[0].id) == []
    assert persons.count == 2


def test_commit_on_search_or_immediate():
    with pytest.raises(ValueError):
        Commit(immediate=True, on_search=True)
