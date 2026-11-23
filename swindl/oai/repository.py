## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines sjdbl's files and sil's index
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "swindl"
#
# "swindl" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

"""The OAI administration of a repository, as meresco-oai's OaiJazz kept it, in the
application's Store: per identifier its metadata prefixes and sets, which of those it
is deleted in, and a stamp (microseconds, unique, increasing) for every change. Store
it in the same transaction as the application's own data:

    oai = Oai(store, "full", always_delete_in_prefixes=["didl"])
    with store.transaction():
        store.put(record)
        oai.add(record.identifier, prefixes=["didl", "oai_dc"], sets=["genre:zuyd"])
"""

import hashlib
import time
from datetime import datetime, timezone

from sil.indexfield import IndexField
from sjdbl.field import Field

from ..store import Base
from ..store.store import QueryParams

SET_HIERARCHY_SEPARATOR = ":"
# a datestamp has seconds: the stamp in microseconds divided by this
STAMP_PER_SECOND = 1_000_000


class OaiRecord(Base):
    """One identifier in one repository. sets has every level of a hierarchical set
    ("genre:zuyd" gives "genre" too); deleted_* are the prefixes and sets it is
    deleted in; tombstone: deleted in all of them (or deleted as a whole)."""

    FIELDS = Base.FIELDS + [
        Field.str("repository"),
        Field.str("identifier"),
        Field.int("stamp"),
        Field.set("prefixes"),
        Field.set("deleted_prefixes"),
        Field.set("sets"),
        Field.set("deleted_sets"),
        Field.bool("tombstone", False),
    ]
    INDEX = Base.INDEX + [
        IndexField.untokenized("repository"),
        IndexField.untokenized("identifier"),
        IndexField.int("stamp", sortable=True),
        IndexField.untokenized("prefixes"),
        IndexField.untokenized("sets"),
    ]

    def index_values(self):
        values = super().index_values()
        values.update(
            repository=self.repository,
            identifier=self.identifier,
            stamp=self.stamp,
            prefixes=sorted(self.prefixes),
            sets=sorted(self.sets),
        )
        return values

    def is_deleted_for(self, prefix, sets=None):
        """Deleted as it is listed for prefix (and the sets asked for, when deleting
        in sets is on: deleted in all of the sets asked for that it is in)."""
        if self.tombstone or prefix in self.deleted_prefixes:
            return True
        if sets is not None and (matching := set(sets) & self.sets):
            return not (matching - self.deleted_sets)
        return False

    @property
    def datestamp(self):
        return datestamp(self.stamp)


class OaiRepository(Base):
    """The metadata formats (prefix: {"schema", "namespace"}) and sets (spec: name)
    of a repository; every prefix and set used is in it."""

    FIELDS = Base.FIELDS + [
        Field.str("repository"),
        Field.json("formats", default=dict),
        Field.json("sets", default=dict),
    ]


MODELS = [OaiRecord, OaiRepository]


class Oai:
    """The OAI administration of one repository (a name; a Store can hold several).
    Add MODELS to the Store's models. Changes are done in a transaction of their own,
    or in the one the caller has open."""

    def __init__(
        self,
        store,
        repository,
        always_delete_in_prefixes=(),
        delete_in_sets=False,
    ):
        self._store = store
        self.repository = repository
        self._always_delete_in_prefixes = set(always_delete_in_prefixes)
        # deleting in sets is not in the OAI-PMH standard: only when asked for
        self.supports_delete_in_sets = delete_in_sets
        self._info = store.get(
            f"OaiRepository:{_id(repository)}", include_archived=True
        )
        if self._info is None:
            self._info = OaiRepository.from_storage(
                store,
                {"meta": {"__id__": _id(repository)}, "data": {}},
            )
            self._info.update(repository=repository)
        self._newest_stamp = self._last_stamp()

    # --- changes ---

    def add(self, identifier, prefixes, sets=()):
        """The record is in these prefixes and sets (besides those it was in); it is
        no longer deleted in them."""
        if not identifier:
            raise ValueError("Empty identifier not allowed.")
        if not prefixes:
            raise ValueError(f"No metadataPrefix for record {identifier!r}")
        sets = _with_supersets(_valid(sets))
        with self._store.transaction():
            record = self._record(identifier)
            prefixes = set(prefixes)
            record.update(
                prefixes=record.prefixes | prefixes,
                deleted_prefixes=record.deleted_prefixes - prefixes,
                sets=record.sets | sets,
                deleted_sets=record.deleted_sets - sets,
            )
            self._save(record)

    def delete(self, identifier, prefixes=(), sets=()):
        """The record is deleted, in all its prefixes and sets, and in
        always_delete_in_prefixes and the prefixes and sets given (also when it was
        not in them). An unknown identifier without prefixes to delete in is
        ignored."""
        if not identifier:
            raise ValueError("Empty identifier not allowed.")
        prefixes = self._always_delete_in_prefixes | set(prefixes)
        with self._store.transaction():
            record = self._find(identifier)
            if record is None and not prefixes:
                if sets:
                    raise ValueError(
                        "setSpec not allowed for an unknown record without prefixes"
                    )
                return
            record = record or self._new(identifier)
            all_prefixes = record.prefixes | prefixes
            all_sets = record.sets | _with_supersets(_valid(sets))
            record.update(
                prefixes=all_prefixes,
                deleted_prefixes=all_prefixes,
                sets=all_sets,
                deleted_sets=all_sets,
            )
            self._save(record, tombstone=True)

    def delete_in_prefixes(self, identifier, prefixes):
        """The record is deleted in these prefixes only (and is in them, deleted)."""
        if not identifier:
            raise ValueError("Empty identifier not allowed.")
        if not prefixes:
            raise ValueError("Empty prefixes not allowed.")
        with self._store.transaction():
            record = self._record(identifier)
            record.update(
                prefixes=record.prefixes | set(prefixes),
                deleted_prefixes=record.deleted_prefixes | set(prefixes),
            )
            self._save(record)

    def delete_in_sets(self, identifier, sets):
        """The record is deleted in these sets only (not standard OAI-PMH: needs
        delete_in_sets=True). An unknown identifier is ignored."""
        if not self.supports_delete_in_sets:
            raise ValueError("Deleting in sets not supported.")
        if not identifier:
            raise ValueError("Empty identifier not allowed.")
        with self._store.transaction():
            record = self._find(identifier)
            if record is None:
                return
            # as OaiJazz: the sets as given, not their supersets
            record.update(
                sets=record.sets | set(sets),
                deleted_sets=record.deleted_sets | set(sets),
            )
            self._save(record)

    def update_format(self, prefix, schema, namespace):
        formats = dict(self._info.formats)
        formats[prefix] = {"schema": schema, "namespace": namespace}
        with self._store.transaction():
            self._info.update(formats=formats)
            self._store.put(self._info)

    def update_set(self, spec, name):
        sets = dict(self._info.sets)
        sets[spec] = name
        with self._store.transaction():
            self._info.update(sets=sets)
            self._store.put(self._info)

    # --- reading ---

    def get(self, identifier):
        """The OaiRecord of identifier, or None."""
        return self._find(identifier)

    @property
    def formats(self):
        """{prefix: {"schema", "namespace"}}, every prefix used included."""
        return dict(self._info.formats)

    @property
    def sets(self):
        """{spec: name}, every set used included ("" when it has no name)."""
        return dict(self._info.sets)

    def select(
        self, prefix, set=None, continue_after=0, from_=None, until=None, size=200
    ):
        """(records, more): at most size OaiRecords in prefix (and set) with a
        stamp after continue_after and from_ <= stamp <= until (microseconds, None:
        open), in the order of their stamps; more: whether there are more."""
        low = max(continue_after + 1, from_ or 0)
        high = "*" if until is None else until
        filters = {"repository": self.repository, "prefixes": prefix}
        if set is not None:
            filters["sets"] = set
        result = self._store.query(
            QueryParams(
                OaiRecord,
                query=f"stamp:[{low} TO {high}]",
                filters=filters,
                sort=[{"field": "stamp"}],
                size=size + 1,
            )
        )
        return result.objs[:size], len(result.objs) > size

    def earliest_stamp(self):
        """The smallest stamp in the repository, or None when it is empty."""
        result = self._store.query(
            QueryParams(
                OaiRecord,
                filters={"repository": self.repository},
                sort=[{"field": "stamp"}],
                size=1,
            )
        )
        return result.objs[0].stamp if result.objs else None

    # --- internal ---

    def _last_stamp(self):
        result = self._store.query(
            QueryParams(
                OaiRecord,
                filters={"repository": self.repository},
                sort=[{"field": "stamp", "reverse": True}],
                size=1,
            )
        )
        return result.objs[0].stamp if result.objs else 0

    def _new_stamp(self):
        stamp = time.time_ns() // 1000
        if stamp <= self._newest_stamp:
            stamp = self._newest_stamp + 1
        self._newest_stamp = stamp
        return stamp

    def _find(self, identifier):
        return self._store.get(
            f"OaiRecord:{_id(self.repository, identifier)}", include_archived=True
        )

    def _new(self, identifier):
        record = OaiRecord.from_storage(
            self._store,
            {"meta": {"__id__": _id(self.repository, identifier)}, "data": {}},
        )
        record.update(repository=self.repository, identifier=identifier)
        return record

    def _record(self, identifier):
        return self._find(identifier) or self._new(identifier)

    def _save(self, record, tombstone=False):
        """A new stamp, the tombstone worked out, put; prefixes and sets known."""
        record.update(
            stamp=self._new_stamp(),
            tombstone=tombstone
            or bool(record.deleted_sets and record.sets == record.deleted_sets)
            or record.prefixes == record.deleted_prefixes,
        )
        self._store.put(record)
        formats = dict(self._info.formats)
        sets = dict(self._info.sets)
        for prefix in record.prefixes - set(formats):
            formats[prefix] = {"schema": "", "namespace": ""}
        for spec in record.sets - set(sets):
            sets[spec] = ""
        if formats != self._info.formats or sets != self._info.sets:
            self._info.update(formats=formats, sets=sets)
            self._store.put(self._info)


def datestamp(stamp):
    """A stamp (microseconds) as an OAI-PMH datestamp, to the second."""
    moment = datetime.fromtimestamp(stamp // STAMP_PER_SECOND, tz=timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _id(*parts):
    """An object id for a repository (and identifier): identifiers can hold any
    character, ids can not."""
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()[:40]


def _valid(sets):
    for spec in sets:
        if "," in spec:
            raise ValueError(f"SetSpec {spec!r} contains illegal characters")
    return sets


def _with_supersets(sets):
    """Every set with the sets above it: "a:b:c" gives "a:b:c", "a:b" and "a"."""
    result = set()
    for spec in sets:
        levels = spec.split(SET_HIERARCHY_SEPARATOR)
        for depth in range(1, len(levels) + 1):
            result.add(SET_HIERARCHY_SEPARATOR.join(levels[:depth]))
    return result
