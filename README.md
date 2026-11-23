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

Install with `pip install swindl`. It needs Python 3.11 or newer; sjdbl, sil
(`seecr-sil`) and their dependencies come with it.

- [reference](https://github.com/seecr/swindl/blob/master/doc/reference.md): everything.
- [guarantees](https://github.com/seecr/swindl/blob/master/doc/guarantees.md): what is
  promised, what not, the limits, backups.
- [WebAdapter](https://github.com/seecr/swindl/blob/master/doc/webadapter.md): the
  WebAdapter in full.
- [examples](https://github.com/seecr/swindl/tree/master/examples): runnable examples,
  and [examples/collection](https://github.com/seecr/swindl/tree/master/examples/collection):
  an application to keep track of a record (or LEGO) collection, built on SWL and swindl.
- [changelog](https://github.com/seecr/swindl/blob/master/CHANGELOG.md): what changed,
  and how to upgrade.

MIT licensed, see [LICENSE](https://github.com/seecr/swindl/blob/master/LICENSE). By
[Seecr](https://seecr.nl).
