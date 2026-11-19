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

import asyncio
import logging
import os
import threading
from collections import OrderedDict
from contextlib import contextmanager

from sil.index import Index
from sil.indexfield import IndexField
from sil.indexprofile import IndexProfile
from sjdbl.base import __ARCHIVED__, __ID__, Base

logger = logging.getLogger(__name__)

# How many objects Indexes remembers the last indexed values of (see add_record)
INDEXED_CACHE_SIZE = 10000


class Commit:
    """When changes become searchable:

    - Commit(): every `timeout` seconds (0: only at shutdown);
    - Commit(immediate=True): at the end of every transaction;
    - Commit(on_search=True): just before a search, when something changed since the
      last commit: a save costs no commit, and a search finds everything saved before
      it. Many saves without a search in between share one commit. The timer still
      commits changes that no search asks for (timeout=0: none)."""

    def __init__(self, timeout=5, immediate=False, on_search=False):
        if immediate and on_search:
            raise ValueError("Commit: immediate or on_search, not both")
        self.timeout = timeout
        self.immediate = immediate
        self.on_search = on_search


class PendingLog:
    """The qids whose index entry may not match their file yet: added (and synced)
    before their files are committed, emptied after the index committed. After a crash
    these, and only these, are indexed again from the files."""

    def __init__(self, path):
        self._path = path

    def add(self, qids):
        if not qids:
            return
        new = not self._path.exists()
        with self._path.open("a") as fp:
            fp.write("".join(f"{qid}\n" for qid in qids))
            fp.flush()
            os.fsync(fp.fileno())
        if new:
            _fsync_dir(self._path.parent)

    def qids(self):
        if not self._path.exists():
            return []
        # a line without its newline was being written when the process died: its
        # files were not committed yet
        lines = self._path.read_text().split("\n")[:-1]
        return list(dict.fromkeys(line for line in lines if line))

    def clear(self):
        if self._path.exists() and self._path.stat().st_size > 0:
            # not synced: if the truncate is lost, some qids are indexed once more
            os.truncate(self._path, 0)


class Indexes:
    """One sil Index per model with an INDEX. swindl commits them itself (sil's own
    commit task is off), so it knows when the pending log can be emptied."""

    def __init__(self, path, models, commit=None, lock=None):
        if commit is None:
            commit = Commit()

        self._path = path
        self._immediate = commit.immediate
        self.on_search = commit.on_search
        self.sees_changes_at_once = commit.immediate or commit.on_search
        # held while changing and committing: Store passes its own lock, so a commit
        # never empties the pending log in the middle of a transaction
        self._lock = lock or threading.RLock()
        self._deferred = 0
        self._changed = set()  # the indexes with changes that are not committed
        self._pending = PendingLog(path / "pending.log")
        self._indexes = {}
        # qid -> the values last given to the index for it: a put that changes no
        # indexed value skips the index (and its commit). Bounded; forgetting only
        # means the next put indexes again. Used with self._lock held.
        self._indexed = OrderedDict()
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
                commit_timeout=0,
                immediate_commit=False,
            )

        self._commit_task = None
        if not commit.immediate and commit.timeout > 0:
            self._commit_task = asyncio.create_task(self._auto_commit(commit.timeout))
            logger.info(f"Indexes: auto-commit every {commit.timeout} seconds")

    async def _auto_commit(self, timeout):
        while True:
            await asyncio.sleep(timeout)
            try:
                await asyncio.to_thread(self.commit)
            except Exception:
                # keep committing: an uncaught error would end this task silently
                logger.exception("Commit failed; retrying after the timeout")

    def commit(self):
        """Commits every index with changes, then empties the pending log."""
        with self._lock:
            changed, self._changed = self._changed, set()
            for index in changed:
                index.commit(immediate_commit=True)
            self._pending.clear()

    @contextmanager
    def deferred(self):
        """With Commit(immediate=True): one commit at the end of the (outermost)
        block instead of one per change."""
        with self._lock:
            self._deferred += 1
            try:
                yield
            finally:
                self._deferred -= 1
            self._commit_if_immediate()

    def _commit_before_search(self):
        if self.on_search and self._changed:
            self.commit()  # (which checks again, with the lock held)

    def _commit_if_immediate(self):
        if self._immediate and not self._deferred:
            self.commit()

    def add_pending(self, qids):
        self._pending.add(qids)

    def pending(self):
        return self._pending.qids()

    def shutdown(self):
        if self._commit_task is not None:
            self._commit_task.cancel()
        self.commit()
        for index in self._indexes.values():
            index.shutdown()

    def delete_all(self):
        with self._lock:
            self._indexed.clear()
            for index in self._indexes.values():
                index.delete_all()
                self._changed.add(index)
            self._commit_if_immediate()

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
            qid = obj.qid
            with self._lock:
                if self._indexed.get(qid) == index_values:
                    # e.g. a changed field that is not indexed: the index has it
                    self._indexed.move_to_end(qid)
                    return
                index.add_record(qid, index_values)
                self._changed.add(index)
                self._remember(qid, index_values)
                self._commit_if_immediate()

    def _remember(self, qid, index_values):
        # index values are plain values or lists of them: copying the lists is enough
        # (a deepcopy took 6% of a bulk load)
        self._indexed[qid] = {
            name: list(value) if isinstance(value, list) else value
            for name, value in index_values.items()
        }
        self._indexed.move_to_end(qid)
        while len(self._indexed) > INDEXED_CACHE_SIZE:
            self._indexed.popitem(last=False)

    def delete_record(self, obj):
        """The record of an object, a reference to one (Proxy) or a qid ("Type:id") out
        of its type's index."""
        qid = obj if isinstance(obj, str) else obj.qid
        with self._lock:
            self._indexed.pop(qid, None)
            if (index := self.get(qid.split(":", 1)[0])) is not None:
                index.delete_record(qid)
                self._changed.add(index)
                self._commit_if_immediate()

    def search_query(self, obj, *args, **kwargs):
        self._commit_before_search()
        if (index := self.get(obj)) is not None:
            return index.search_query(*args, **kwargs)

    def search_by_term(self, obj, *args, **kwargs):
        self._commit_before_search()
        if (index := self.get(obj)) is not None:
            return index.search_by_term(*args, **kwargs)

    def search_by_query(self, obj, query, *args, **kwargs):
        self._commit_before_search()
        if (index := self.get(obj)) is not None:
            built_query = query.build(index)
            return index.search(built_query, *args, **kwargs)

    def search_by_term_and_query(self, obj, field, value, query, *args, **kwargs):
        self._commit_before_search()
        if (index := self.get(obj)) is not None:
            query = index.all_of(
                index.parse_query(query), index.term_query(field, value)
            )
            return index.search(query, *args, **kwargs)

    def suggest(self, obj, *args, **kwargs):
        self._commit_before_search()
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


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
