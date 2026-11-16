# swindl – Seecr Web Index and Database Lib

The storage side of an [SWL](https://github.com/seecr/swl) application: objects in
[sjdbl](https://github.com/seecr/sjdbl)'s JSON files, searchable through
[sil](https://github.com/seecr/sil)'s index, as one `Store`; and the WebAdapter, which
converts and checks what comes in from a web form.

```python
from sjdbl.field import Field
from swindl.store import Base, Store
from swindl.webadapter import Adapt, from_form

class Person(Base):
    FIELDS = [Field.str("name"), Field.date("dob")]
    ADAPTATIONS = [Adapt.date("dob")]

store = Store(data_dir, [Person])
person = store.create(Person, from_form(Person, form, ["name", "dob"]))

with store.transaction():          # stored and indexed together, or not at all
    store.put(person, invoice)
    store.delete(basket)
```

Crash safe: a transaction is in the files completely or not at all, and the index
catches up when the store is opened again. `swindl-check` tells whether the index
matches the files.

- `doc/reference.md`: the reference.
- `doc/guarantees.md`: what is promised, what not, the limits, backups.
- `doc/webadapter.md`: the WebAdapter.
- `examples/`: runnable examples (`PYTHONPATH=. python examples/store.py`), and
  `examples/collection/`: an application to keep track of a record (or LEGO)
  collection, built on SWL and swindl.
- `CHANGELOG.md`: what changed, and how to upgrade.

GPLv2, by [Seecr](https://seecr.nl).
