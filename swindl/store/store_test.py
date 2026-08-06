from .store import Store, HasChangedException
from .indexes import Commit
from .base import Base
from .field import Field
import pytest


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
