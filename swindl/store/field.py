import uuid
from datetime import datetime
import json

ATTR_READONLY = "readonly"


def new_uuid():
    return str(uuid.uuid1())


class Field:

    @classmethod
    def uuid(cls, name, default=new_uuid):
        return cls(
            name=name,
            default=default,
            attributes={ATTR_READONLY: True},
        )

    @classmethod
    def id(cls, name, default=None):
        return cls(
            name=name,
            default=default,
        )

    @classmethod
    def str(cls, name, default=""):
        return cls(name=name, default=default)

    @classmethod
    def int(cls, name, default=0):
        return cls(
            name=name,
            default=default,
        )

    @classmethod
    def text(cls, name, default=""):
        return cls(name=name, default=default)

    @classmethod
    def date(cls, name, default=None):
        return cls(
            name=name,
            default=default,
            to_storage=lambda d: d.isoformat() if d else None,
            from_storage=lambda store, v: (
                datetime.fromisoformat(v).date() if v is not None else None
            ),
        )

    @classmethod
    def bool(cls, name, default):
        return cls(name=name, default=default)

    @classmethod
    def json(cls, name, default=list):
        return cls(
            name=name,
            default=default,
            to_storage=lambda d: json.dumps(d),
            from_storage=lambda store, v: v and json.loads(v),
        )

    @classmethod
    def datetime(cls, name, default=None):
        return cls(
            name=name,
            default=default,
            to_storage=lambda d: d.isoformat() if d else None,
            from_storage=lambda store, v: (
                datetime.fromisoformat(v) if v is not None else None
            ),
        )

    @classmethod
    def reference(cls, name):
        return cls(
            name=name,
            to_storage=lambda v: v and str(v.qid) or None,
            from_storage=lambda store, v: v and store.proxy(qid=v or None),
        )

    @classmethod
    def enum(cls, name, enum, default):
        return cls(
            name=name,
            default=default,
            to_storage=lambda e: e.value,
            from_storage=lambda store, v: enum(v),
        )

    @classmethod
    def collection(cls, name):
        return cls(
            name,
            default=[],
            to_storage=lambda items: [item.qid for item in items],
            from_storage=lambda store, qid_list: [store.proxy(qid) for qid in qid_list],
        )

    def __init__(
        self, name, default=None, to_storage=None, from_storage=None, attributes=None
    ):
        self.name = name
        self.to_storage = to_storage or (lambda value: value)
        self.from_storage = from_storage or (lambda store, value: value)
        self._attributes = attributes or {}
        self._default = default

    @property
    def default(self):
        return self._default() if callable(self._default) else self._default

    @property
    def is_readonly(self):
        return self._attributes.get(ATTR_READONLY, False)
