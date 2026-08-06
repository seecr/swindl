from .jsonstore import JsonStore, EnumerateValue
from .field import Field
from .base import Base
from .store import HasChangedException

from datetime import datetime

from enum import Enum


class GenderEnum(Enum):
    male = 1
    female = 2
    other = 3


class Person(Base):
    ENUMERATORS = [EnumerateValue("number")]
    FIELDS = Base.FIELDS + [
        Field.str("name"),
        Field.int("number"),
        Field.date("dob"),
        Field.reference("parent"),
        Field.enum("gender", GenderEnum, GenderEnum.other),
        Field.bool("long_hair", default=False),
        Field.uuid("gov_id"),
        Field.uuid("secret_id", default=None),
    ]


def test_enumerator_files(tmp_path):
    store = JsonStore(path=tmp_path, models=[Person])

    assert (tmp_path / "Person" / "number.enumerator").is_file()
    assert (tmp_path / "Person" / "number.enumerator").read_text() == "0"

    e = store.enumerator(Person, "number")
    value = e.increment()
    assert value == 0
    assert (tmp_path / "Person" / "number.enumerator").read_text() == "1"


def test_store_create_and_get(tmp_path):
    store = JsonStore(path=tmp_path, models=[Person])

    parent = Person.create(
        name="John Smith",
        dob=datetime.fromisoformat("2000-01-01"),
        gender=GenderEnum.male,
    )
    child = Person.create(
        name="Joe Smith",
        dob=datetime.fromisoformat("2020-01-01"),
        parent=parent,
        long_hair=True,
    )

    store.put(parent, child)

    parent_revisited = store.get(parent.qid)
    assert parent_revisited.__id__ == parent.__id__
    assert parent_revisited.name == "John Smith"
    assert parent_revisited.dob == datetime.fromisoformat("2000-01-01").date()
    assert parent_revisited.gender == GenderEnum.male
    assert parent_revisited.long_hair is False

    child_revisited = store.get(child.qid)
    assert child_revisited.__id__ == child.__id__
    assert child_revisited.parent.qid == parent_revisited.qid
    assert child_revisited.parent.name == "John Smith"
    assert child_revisited.gender == GenderEnum.other
    assert child_revisited.long_hair is True

    child_revisited = store.get(child.qid)
    child_revisited.parent.update(name="Jane Smith", gender=GenderEnum.female)
    store.put(child_revisited.parent)
    parent_revisited = store.get(parent.qid)
    assert parent_revisited.__id__ == parent.__id__
    assert parent_revisited.name == "Jane Smith"

    parent_revisited = store.get(parent.qid)
    assert parent_revisited["name"] == "Jane Smith"
    assert parent_revisited["gender"] == GenderEnum.female

    child_revisited = store.get(child.qid)
    child_revisited.parent["name"] == "Jane Smith"

    child_revisited = store.get(child.qid)
    assert child_revisited.parent == parent_revisited


def test_delete_as_object(tmp_path):
    store = JsonStore(path=tmp_path, models=[Person])

    person = Person.create(name="John Smith", dob=datetime.fromisoformat("2000-01-01"))
    store.put(person)

    person_revisited = store.get(person.qid)
    assert not person_revisited is None

    store.delete(person)
    person_revisited = store.get(person.qid)
    assert person_revisited is None


def test_delete_with_qid(tmp_path):
    store = JsonStore(path=tmp_path, models=[Person])

    person = Person.create(name="John Smith", dob=datetime.fromisoformat("2000-01-01"))
    store.put(person)

    person_revisited = store.get(person.qid)
    assert not person_revisited is None

    store.delete(person.qid)
    person_revisited = store.get(person.qid)
    assert person_revisited is None


def test_list_objects(tmp_path):
    store = JsonStore(path=tmp_path, models=[Person])

    persons = list(store.list(Person))
    assert len(persons) == 0

    store.put(
        Person.create(name="John Smith", dob=datetime.fromisoformat("2000-01-01"))
    )
    persons = list(store.list(Person))
    assert len(persons) == 1


def test_readonly(tmp_path):
    person = Person.create(name="John Smith", dob=datetime.fromisoformat("2000-01-01"))
    person_id = person.__id__

    person.update(__id__="aap")
    assert person.__id__ == person_id


def test_none_for_uuid(tmp_path):
    person = Person.create(name="John Smith", dob=datetime.fromisoformat("2000-01-01"))
    assert person.gov_id is not None
    assert person.secret_id is None
