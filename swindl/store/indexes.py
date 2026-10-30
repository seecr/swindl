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

from sil.index import Index
from sil.indexfield import IndexField
from sil.indexprofile import IndexProfile

from sjdbl.base import Base, __ARCHIVED__, __ID__

import logging

logger = logging.getLogger(__name__)


class Commit:
    def __init__(self, timeout=5, immediate=False):
        self.timeout = timeout
        self.immediate = immediate


class Indexes:
    def __init__(self, path, models, commit=None):
        if commit is None:
            commit = Commit()

        self._path = path
        self._indexes = {}
        for model in models:
            if not issubclass(model, Base) or not hasattr(model, "INDEX"):
                logger.info(f"Skipping {model.type_name}: No index fields defined")
                continue

            model_name = model.__name__
            logger.info(f"Adding {model_name}")

            self._indexes[model_name] = Index(
                self._path / model_name,
                IndexProfile(
                    [
                        IndexField.untokenized(name=__ID__),
                        IndexField.untokenized(name=__ARCHIVED__),
                    ]
                    + model.INDEX
                ),
                commit_timeout=commit.timeout,
                immediate_commit=commit.immediate,
            )

    def shutdown(self):
        for index in self._indexes.values():
            index.shutdown()

    def delete_all(self):
        for index in self._indexes.values():
            index.delete_all()

    def get(self, cls):
        if isinstance(cls, Base):
            type_name = cls.__class__.__name__
        elif isinstance(cls, type) and issubclass(cls, Base):
            type_name = cls.__name__
        elif isinstance(cls, str):
            type_name = cls
        else:
            raise TypeError(f"Base or str type required, got: {cls!r}")

        return self._indexes.get(type_name)

    def add_record(self, obj):
        if (index := self.get(obj)) is not None:
            index_values = obj.index_values()
            index_values[__ID__] = str(obj[__ID__])
            index_values[__ARCHIVED__] = str(obj[__ARCHIVED__])
            index.add_record(obj.qid, index_values)

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
            query = index.all_of(
                index.parse_query(query), index.term_query(field, value)
            )
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

        term_queries = []
        for term in self._terms:
            values = (
                term["value"] if isinstance(term["value"], list) else [term["value"]]
            )
            for value in values:
                term_queries.append(index.term_query(term["field"], value))

        return index.all_of(q, *term_queries)

    def __repr__(self):
        return f"Query({self._query!r}, {self._terms!r})"
