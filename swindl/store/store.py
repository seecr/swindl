## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines swl, sil and sdbl
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "Swindl"
#
# "Swindl" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

import logging
import threading
from contextlib import contextmanager

from seecr_stdlib import first
from sjdbl import Store as JsonStore
from sjdbl.base import __ARCHIVED__, __ID__, __REV__, Base

from .indexes import Indexes, Query
from .utils import mkdir

logger = logging.getLogger(__name__)


class HasChangedException(Exception):
    pass


class QueryParams:
    def __init__(
        self,
        obj_type,
        query="*",
        page=0,
        size=20,
        sort=None,
        filters=None,
        drilldown=None,
    ):
        self.query = query
        self.obj_type = obj_type
        self.page = page
        self.size = size
        self.sort = sort
        self.filters = filters or {}
        self.drilldown = drilldown or {}


class QueryResult:
    def __init__(self, objs, total, params, drilldown):
        self.objs = objs
        self.params = params

        self.start = (params.page * params.size) + 1
        self.stop = min((params.page * params.size) + params.size, total)
        self.total = total
        self.pages = Pages(params.page, params.size, total)
        self.drilldown = drilldown

    def is_last_page(self):
        return self.pages.last is None or self.params.page == self.pages.last

    @property
    def summary(self):
        if self.total == 0:
            return f"{self.total} resultaten"
        elif self.total == 1:
            return f"{self.total} resultaat"

        return f"{self.start} - {self.stop} van {self.total} resultaten"


class Pages:
    def __init__(self, page, size, total):
        self.first = None if page == 0 else 0
        self.prev = None if page == 0 else page - 1
        self.next = None if (page + 1) * size >= total else page + 1
        self.last = (
            None
            if (page + 1) * size >= total
            else total // size if total % size > 0 else (total // size) - 1
        )


class Store(object):
    """Objects in sjdbl's files, searchable through sil's indexes.

    The files are the truth; the index is derived from them. Every change is a
    transaction (see transaction()): its qids go to the pending log, then the files are
    committed (sjdbl, crash safe), then the index follows. After a crash the qids in the
    pending log are indexed again from the files when the store is opened."""

    def __init__(self, path, models, commit=None):
        # Every change holds it around the files and the index, so both see changes in
        # the same order; a commit of the index holds it too.
        self._lock = threading.RLock()
        self._store = JsonStore(path=mkdir(path / "store"), models=models)
        self._indexes = Indexes(
            path=mkdir(path / "index"), models=models, commit=commit, lock=self._lock
        )
        self._tx = None  # qid -> object, or None for a delete, in transaction()
        self._tx_depth = 0
        self._models = {}
        for model in models:
            if not issubclass(model, Base):
                continue
            model_name = model.__name__

            self._models[model_name] = model
        self._recover()

    def _recover(self):
        """Index again what a crash left between the files and the index."""
        if not (qids := self._indexes.pending()):
            return
        with self._lock:
            for qid in qids:
                if (obj := self._store.get(qid)) is None:
                    self._indexes.delete_record(qid)
                else:
                    self._indexes.add_record(obj)
            self._indexes.commit()
        logger.warning(
            f"Indexed {len(qids)} object(s) again that a crash left unindexed"
        )

    def enumerator(self, *args, **kwargs):
        return self._store.enumerator(*args, **kwargs)

    def disconnect(self):
        self._indexes.shutdown()

    def commit(self):
        """Commits the indexes now: what was stored becomes searchable. Needed only with
        Commit(timeout=0); the other modes commit by themselves."""
        self._indexes.commit()

    def create(self, cls, values=None):
        if isinstance(cls, str):
            cls = self._models.get(cls)

        obj = cls(values=values or {})
        self.put(obj)
        return obj

    @contextmanager
    def transaction(self):
        """All puts and deletes of the block are stored together at its end, or none of
        them; also when the process crashes. Then the index follows.

            with store.transaction():
                order.update(state="paid")
                store.put(order, invoice)
                store.delete(basket)

        - An exception in the block discards it: files and index are unchanged, and
          the objects get their old revisions back.
        - Within the block get() sees its puts and deletes (in this thread); query()
          and list() don't, they search the index.
        - With Commit(immediate=True) the index commits once, at the end; otherwise
          the timer commits. A delete is committed at the end of its transaction.
        - Blocks can be nested; the outermost one commits. The store's lock is held for
          the whole block: other threads' changes wait.
        - It is also the fast way to store many objects: one sync of the files and one
          commit of the index, instead of one per put."""
        with self._lock:
            outermost = self._tx is None
            if outermost:
                self._tx = {}
            self._tx_depth += 1
            try:
                with self._store.transaction():
                    yield self
                    if outermost:
                        # before the files are committed (when this block ends)
                        self._indexes.add_pending(list(self._tx))
            except BaseException:
                if outermost:
                    self._tx = None
                raise
            finally:
                self._tx_depth -= 1
            if outermost:
                changes, self._tx = self._tx, None
                self._index(changes)

    def _index(self, changes):
        with self._indexes.deferred():
            for qid, obj in changes.items():
                if obj is None:
                    self._indexes.delete_record(qid)
                else:
                    self._indexes.add_record(obj)
        if None in changes.values() and not self._indexes.on_search:
            self._indexes.commit()  # a delete is searchable at once

    def put(self, *objs):
        with self.transaction():
            self._store.put(*objs)
            for obj in objs:
                self._tx[obj.qid] = obj

    def _class(self, cls):
        if isinstance(cls, Base):
            return cls.__class__.__name__
        elif isinstance(cls, str):
            return cls
        else:
            return cls.__name__

    def _get(self, qid_or_qrid):
        cls, _, identifier = qid_or_qrid.partition(":")
        identifier, _, revision = identifier.partition(":")

        if (record := self._store.get(f"{cls}:{identifier}")) is not None:
            if revision != "" and record[__REV__] != revision:
                raise HasChangedException()

        return record

    def get(self, qid_or_qrid, include_archived=False, assert_type=None):
        if (record := self._get(qid_or_qrid)) is None:
            return None

        if not include_archived and record[__ARCHIVED__]:
            return None

        if assert_type is not None and self._class(record) != self._class(assert_type):
            raise TypeError(f"Expected {assert_type!r}, got {self._class(record)!r}")
        return record

    def list(self, cls, include_archived=False, **kwargs):
        qp = QueryParams(cls)
        for name, value in kwargs.items():
            qp.filters[name] = value

        if not include_archived:
            qp.filters[__ARCHIVED__] = str(False)

        result = self.query(qp)
        while True:
            for obj in result.objs:
                yield obj
            if result.is_last_page():
                break
            qp = result.params
            qp.page = qp.page + 1
            result = self.query(qp)

    def find_one(self, cls, **kwargs):
        qp = QueryParams(cls)
        for name, value in kwargs.items():
            qp.filters[name] = value
        result = self.query(qp)
        return first(result.objs)

    def find_by_field(self, cls, field, value):
        results = self._indexes.search_by_term(cls, field, value)

        return self._objects(results["docs"])

    def _objects(self, docs):
        """The objects of index hits. A hit without a file (deleted between the search
        and the read, or left in the index by a crash) is skipped."""
        return [obj for doc in docs if (obj := self._get(doc[__ID__])) is not None]

    def query(self, query_params):
        objs = []
        obj_type = query_params.obj_type

        if isinstance(query_params.query, str):
            query = Query(query_params.query)
        elif isinstance(query_params.query, Query):
            query = query_params.query
        else:
            raise RuntimeError("Unknown query")

        for name, value in query_params.filters.items():
            if value:
                query.add_term(name, value)

        results = self._indexes.search_by_query(
            obj_type,
            query,
            page=query_params.page + 1,
            limit=query_params.size,
            sort=query_params.sort,
            drilldown=query_params.drilldown,
        )

        total = results["count"]

        objs = self._objects(results["docs"])

        return QueryResult(
            objs=objs, total=total, params=query_params, drilldown=results["drilldown"]
        )

    def delete(self, obj):
        """Removes it from the files and the index: an object, a reference to one (a
        Proxy, as references and collections give; nothing is loaded) or its qid."""
        qid = obj if isinstance(obj, str) else obj.qid
        with self.transaction():
            self._store.delete(obj if isinstance(obj, Base) else qid)
            self._tx[qid] = None

    def archive(self, obj):
        obj.mark_archived(self)

    def reindex(self, models):
        with self._lock, self._indexes.deferred():
            self._indexes.delete_all()
            for model in models:
                if not hasattr(model, "INDEX"):
                    continue
                logger.info(f"Reindexing {model.__name__}")
                records = self._store.list(model)
                for record in records:
                    logger.info(f"Reindexing {record.qid}")
                    self._indexes.add_record(record)
            self._indexes.commit()
