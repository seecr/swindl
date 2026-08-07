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

from .field import Field
from .utils import new_uuid

from sil.indexfield import IndexField

__ID__ = "__id__"
__REV__ = "__rev__"
__ARCHIVED__ = "__archived__"


class Base:
    META = [
        Field.uuid(__ID__),
        Field.uuid(__REV__),
        Field.bool(__ARCHIVED__, default=False),
    ]
    FIELDS = []
    INDEX = []

    def __init__(self, values=None):
        self._meta = {field.name: field.default for field in self.META}
        self._data = {field.name: field.default for field in self.FIELDS}
        if values is not None:
            for field in self.FIELDS:
                if (value := values.get(field.name)) is not None:
                    self._data[field.name] = value

    def index_values(self):
        return {}

    @classmethod
    def create(cls, **kwargs):
        return cls(values=kwargs)

    @property
    def id(self):
        return self._meta[__ID__]

    @property
    def is_archived(self):
        return self._meta[__ARCHIVED__]

    @property
    def type_name(self):
        return self.__class__.__name__

    @property
    def qid(self):
        return f"{self.type_name}:{self[__ID__]}"

    @property
    def qrid(self):
        return f"{self.type_name}:{self[__ID__]}:{self[__REV__]}"

    def update(self, **kwargs):
        changed = False
        for field in self.FIELDS:
            if field.is_readonly or field.name not in kwargs:
                continue

            value = kwargs.get(field.name)
            if self._data[field.name] != value:
                self._data[field.name] = value
                changed = True
        if changed:
            self._meta[__REV__] = new_uuid()
        return changed

    def delete(self, store):
        store.delete(self)

    def archive(self, store):
        store.archive(self)

    def deletable(self, store):
        return True

    def mark_archived(self, store, archived=True):
        self._meta[__ARCHIVED__] = archived
        store.put(self)

    def __getattr__(self, name):
        if name.startswith("__") and name in self._meta:
            return self._meta[name]

        if name in self._data:
            return self._data[name]
        return getattr(super(), name)

    def __getitem__(self, name):
        if name.startswith("__") and name in self._meta:
            return self._meta[name]

        if name in self._data:
            return getattr(self, name)
        raise KeyError(name)

    def to_storage(self):
        return {
            "data": {
                field.name: field.to_storage(self._data[field.name])
                for field in self.FIELDS
            },
            "meta": {
                field.name: field.to_storage(self._meta[field.name])
                for field in self.META
            },
        }

    @classmethod
    def from_storage(cls, store, record):
        obj = cls()
        obj._meta.update(
            {
                field.name: field.from_storage(store, record["meta"][field.name])
                for field in cls.META
                if field.name in record["meta"]
            }
        )
        obj._data.update(
            {
                field.name: field.from_storage(store, record["data"][field.name])
                for field in cls.FIELDS
                if field.name in record["data"]
            }
        )
        return obj

    def __eq__(self, other):
        return other.id == self.id if isinstance(other, self.__class__) else False


class Proxy:
    def __init__(self, store, qid):
        self.qid = qid
        self.store = store

    def deproxy(self):
        if (obj := self.store.get(self.qid)) is None:
            raise ValueError(f"No object to deproxy: {self.qid}")
        object.__setattr__(self, "__class__", obj.__class__)
        object.__setattr__(self, "__dict__", obj.__dict__)

    def __getattr__(self, name):
        self.deproxy()
        return getattr(self, name)

    def __getitem__(self, name):
        self.deproxy()
        return self.__getitem__(name)

    def __eq__(self, other):
        return isinstance(other, (Base, Proxy)) and self.qid == other.qid
