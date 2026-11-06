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
```

- `doc/reference.md`: the reference.
- `doc/webadapter.md`: the WebAdapter.
- `examples/`: runnable examples (`PYTHONPATH=. python examples/store.py`).
- `CHANGELOG.md`: what changed, and how to upgrade.

GPLv2, by [Seecr](https://seecr.nl).
