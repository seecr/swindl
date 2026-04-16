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

from sil.index import Index
from sil.indexprofile import IndexProfile
from sdbl.base import Base

from org.apache.lucene.search import BooleanQuery, TermQuery
from org.apache.lucene.search import BooleanClause
from org.apache.lucene.index import Term


class Indexes:
    def __init__(self, path, models, commit_timeout=5, immediate_commit=False):
        self._path = path
        self._indexes = {}
        for model in models:
            if not issubclass(model, Base) or not hasattr(model, "INDEX"):
                print(f"* Skipping {model.type_name}: No index fields defined")
                continue

            self._indexes[model.type_name] = Index(
                path / model.type_name,
                IndexProfile(model.INDEX),
                commit_timeout=commit_timeout,
                immediate_commit=immediate_commit,
            )

    def shutdown(self):
        for index in self._indexes.values():
            index.shutdown()

    def delete_all(self):
        for index in self._indexes.values():
            index.delete_all()

    def get(self, cls):
        if isinstance(cls, Base) or hasattr(cls, "type_name"):
            type_name = cls.type_name
        elif isinstance(cls, str):
            type_name = cls
        else:
            raise TypeError(f"Base or str type required, got: {cls!r}")

        return self._indexes.get(type_name)

    async def add_record(self, store, obj):
        if (index := self.get(obj)) is not None:
            values = await obj.index_values(store)
            await index.add_record(obj.qid, values)

    def delete_record(self, obj):
        if (index := self.get(obj)) is not None:
            index.delete_record(obj.qid, immediate_commit=True)

    def search_query(self, obj, *args, **kwargs):
        if (index := self.get(obj)) is not None:
            return index.search_query(*args, **kwargs)

    def search_by_term(self, obj, *args, **kwargs):
        if (index := self.get(obj)) is not None:
            return index.search_by_term(*args, **kwargs)

    def search_by_query(self, obj, query, *args, **kwargs):
        if (index := self.get(obj)) is not None:
            built_query = query.build(index)
            return index.search(built_query, *args, **kwargs)

    def search_by_term_and_query(self, obj, field, value, query, *args, **kwargs):
        if (index := self.get(obj)) is not None:
            q = index.parse_query(query)
            t = TermQuery(Term(field, value))
            builder = BooleanQuery.Builder()
            builder.add(BooleanClause(q, BooleanClause.Occur.MUST))
            builder.add(BooleanClause(t, BooleanClause.Occur.MUST))
            query = builder.build()
            return index.search(query, *args, **kwargs)

    def suggest(self, obj, *args, **kwargs):
        if (index := self.get(obj)) is not None:
            return index.suggest(*args, **kwargs)

    def sortfields_for(self, obj):
        if (index := self.get(obj)) is not None:
            return index.sortfields
        return []


class Query:
    def __init__(self, query):
        self._terms = []
        self._query = query

    def add_term(self, field, value):
        self._terms.append(dict(field=field, value=value))

    def build(self, index):
        q = index.parse_query(self._query)
        if self._terms == []:
            return q

        builder = BooleanQuery.Builder()
        builder.add(BooleanClause(q, BooleanClause.Occur.MUST))

        for term in self._terms:
            t = TermQuery(Term(term["field"], term["value"]))
            builder.add(BooleanClause(t, BooleanClause.Occur.MUST))

        return builder.build()

    def __repr__(self):
        return f"Query({self._query!r}, {self._terms!r})"
