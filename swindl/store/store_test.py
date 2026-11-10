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


def test_batch_commits_once_per_index_at_the_end(tmp_path):
    store = Store(tmp_path, [Person, Pet], commit=Commit(immediate=True))
    persons, pets = _counted(store, Person), _counted(store, Pet)
    with store.batch():
        people = [store.create(Person, values={"name": f"p{nr}"}) for nr in range(5)]
        store.create(Pet, values={"name": "Rex"})
        assert (persons.count, pets.count) == (0, 0)
        assert list(store.list(Person)) == []  # the index: not yet
        assert store.get(people[0].qid).name == "p0"  # the files: at once
    assert (persons.count, pets.count) == (1, 1)
    assert len(list(store.list(Person))) == 5

    with store.batch():  # nested: the outermost commits
        with store.batch():
            store.create(Person, values={"name": "p5"})
        store.create(Person, values={"name": "p6"})
        assert persons.count == 1
    assert persons.count == 2

    with store.batch():  # nothing indexed changed: no commit
        store.put(people[0])
    assert persons.count == 2

    store.create(Person, values={"name": "p7"})  # after a block: as before
    assert persons.count == 3


def test_batch_commits_when_it_raises_and_deletes_at_once(tmp_path):
    store = Store(tmp_path, [Person], commit=Commit(immediate=True))
    persons = _counted(store, Person)
    gone = store.create(Person, values={"name": "gone"})
    with pytest.raises(ValueError):
        with store.batch():
            store.delete(gone)  # a delete is committed at once
            assert persons.count == 2 and list(store.list(Person)) == []
            store.create(Person, values={"name": "kept"})
            raise ValueError("oops")
    assert persons.count == 3
    assert [p.name for p in store.list(Person)] == ["kept"]
