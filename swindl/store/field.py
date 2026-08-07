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

from datetime import datetime
from .utils import new_uuid
import json

ATTR_READONLY = "readonly"


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
