## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines swl, sil and sdbl
#
# Copyright (C) 2025-2026 Seecr (Seek You Too B.V.) https://seecr.nl
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

from .indexes import Indexes

from sdbl import Base, Field
from sil.indexfield import IndexField


class Obj(Base):
    FIELDS = Base.FIELDS + [Field.str("something")]
    INDEX = [IndexField.unqualified(name="ALL"), IndexField.text(name="something")]

    async def index_values(self, store):
        return dict(something=self.something, ALL=self.something)


async def test_indexes(tmp_path):
    indexes = Indexes(tmp_path, [Obj], immediate_commit=True)

    assert indexes.get("Obj") is not None
    assert indexes.get(Obj) is not None

    obj = Obj()
    assert indexes.get(obj) is not None


async def test_add_query_delete(tmp_path):
    indexes = Indexes(tmp_path, [Obj], immediate_commit=True)
    assert indexes.search_query(Obj, "*") == {"count": 0, "docs": [], "drilldown": {}}

    obj = Obj()
    obj.update(something="tekst")
    await indexes.add_record(store=None, obj=obj)

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


async def test_delete(tmp_path):
    indexes = Indexes(tmp_path, [Obj], immediate_commit=True)
    assert indexes.search_query(Obj, "*") == {"count": 0, "docs": [], "drilldown": {}}

    obj = Obj()
    obj.update(something="tekst")
    await indexes.add_record(store=None, obj=obj)

    result = indexes.search_query(Obj, "*")
    assert result["count"] == 1
    assert result["docs"][0]["__id__"] == obj.qid

    indexes.delete_record(cls=Obj, identifier=obj.id)
    assert indexes.search_query(Obj, "*") == {"count": 0, "docs": [], "drilldown": {}}
