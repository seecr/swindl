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

from sil.indexfield import IndexField
from sjdbl.field import Field

from .base import Base
from .indexes import Commit, Indexes


class Obj(Base):
    FIELDS = Base.FIELDS + [Field.str("something")]
    INDEX = [IndexField.unqualified(name="ALL"), IndexField.text(name="something")]

    def index_values(self):
        return dict(something=self.something, ALL=self.something)


def test_indexes(tmp_path):
    indexes = Indexes(tmp_path, [Obj], Commit(immediate=True))

    assert indexes.get("Obj") is not None
    assert indexes.get(Obj) is not None

    obj = Obj()
    assert indexes.get(obj) is not None


def test_add_query_delete(tmp_path):
    indexes = Indexes(tmp_path, [Obj], Commit(immediate=True))
    assert indexes.search_query(Obj, "*") == {"count": 0, "docs": [], "drilldown": {}}

    obj = Obj()
    obj.update(something="tekst")
    indexes.add_record(obj=obj)

    result = indexes.search_query(Obj, "*")
    assert result["count"] == 1
    assert result["docs"][0]["__id__"] == obj.qid

    result = indexes.search_query(Obj, "tekst")
    assert result["count"] == 1
    assert result["docs"][0]["__id__"] == obj.qid

    result = indexes.search_query(Obj, "nothing")
    assert result == {"count": 0, "docs": [], "drilldown": {}}

    indexes.delete_record(obj=obj)
    assert indexes.search_query(Obj, "*") == {"count": 0, "docs": [], "drilldown": {}}


def _count_index_adds(indexes, monkeypatch):
    index = indexes.get(Obj)
    added = []
    original = index.add_record

    def add_record(*args, **kwargs):
        added.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(index, "add_record", add_record)
    return added


def test_unchanged_index_values_skip_the_index(tmp_path, monkeypatch):
    indexes = Indexes(tmp_path, [Obj], Commit(immediate=True))
    added = _count_index_adds(indexes, monkeypatch)

    obj = Obj()
    obj.update(something="tekst")
    indexes.add_record(obj=obj)
    indexes.add_record(obj=obj)  # nothing indexed changed: no index update
    assert added == [obj.qid]

    obj.update(something="andere tekst")
    indexes.add_record(obj=obj)
    assert added == [obj.qid, obj.qid]
    assert indexes.search_query(Obj, "andere")["count"] == 1
    assert indexes.search_query(Obj, "tekst")["count"] == 1

    indexes.delete_record(obj)  # gone from the index: the next add indexes again
    assert indexes.search_query(Obj, "*")["count"] == 0
    indexes.add_record(obj=obj)
    assert len(added) == 3
    assert indexes.search_query(Obj, "*")["count"] == 1

    indexes.delete_all()
    indexes.add_record(obj=obj)
    assert len(added) == 4
    assert indexes.search_query(Obj, "*")["count"] == 1


def test_remembered_values_are_bounded(tmp_path, monkeypatch):
    from . import indexes as indexes_module

    monkeypatch.setattr(indexes_module, "INDEXED_CACHE_SIZE", 2)
    indexes = Indexes(tmp_path, [Obj], Commit(immediate=True))
    added = _count_index_adds(indexes, monkeypatch)
    objs = []
    for word in ["een", "twee", "drie"]:
        obj = Obj()
        obj.update(something=word)
        indexes.add_record(obj=obj)
        objs.append(obj)
    assert len(indexes._indexed) == 2
    indexes.add_record(obj=objs[0])  # forgotten: indexed again (harmless)
    indexes.add_record(obj=objs[2])  # remembered: skipped
    assert added == [o.qid for o in objs] + [objs[0].qid]
    assert indexes.search_query(Obj, "*")["count"] == 3
