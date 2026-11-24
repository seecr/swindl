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

import pytest
from sjdbl.field import Field

from ..store import Base
from ..store.indexes import Commit
from ..store.store import Store
from .repository import MODELS, Oai, datestamp


class Document(Base):
    FIELDS = Base.FIELDS + [Field.str("title")]


def new_store(path):
    return Store(path, MODELS + [Document], commit=Commit(immediate=True))


@pytest.fixture
def store(tmp_path):
    return new_store(tmp_path)


def listed(oai, prefix, set=None, **kwargs):
    records, _ = oai.select(prefix, set=set, **kwargs)
    return [(r.identifier, r.is_deleted_for(prefix)) for r in records]


def test_add_and_select_in_the_order_of_changes(store):
    oai = Oai(store, "full")
    oai.add("id:2", prefixes=["didl"])
    oai.add("id:1", prefixes=["didl", "oai_dc"])
    oai.add("id:2", prefixes=["didl"])  # changed again: last
    assert listed(oai, "didl") == [("id:1", False), ("id:2", False)]
    assert listed(oai, "oai_dc") == [("id:1", False)]
    assert listed(oai, "mods") == []
    assert oai.formats == {
        "didl": {"schema": "", "namespace": ""},
        "oai_dc": {"schema": "", "namespace": ""},
    }


def test_stamps_are_unique_and_increase(store):
    oai = Oai(store, "full")
    for nr in range(50):
        oai.add(f"id:{nr}", prefixes=["didl"])
    records, more = oai.select("didl", size=100)
    stamps = [r.stamp for r in records]
    assert stamps == sorted(stamps) and len(set(stamps)) == 50
    assert not more
    assert records[0].datestamp == datestamp(records[0].stamp)
    assert oai.earliest_stamp() == stamps[0]


def test_select_parts_and_ranges(store):
    oai = Oai(store, "full")
    for nr in range(5):
        oai.add(f"id:{nr}", prefixes=["didl"])
    first, more = oai.select("didl", size=2)
    assert [r.identifier for r in first] == ["id:0", "id:1"] and more
    rest, more = oai.select("didl", continue_after=first[-1].stamp, size=10)
    assert [r.identifier for r in rest] == ["id:2", "id:3", "id:4"] and not more
    stamps = [r.stamp for r in first + rest]
    middle, _ = oai.select("didl", from_=stamps[1], until=stamps[3])
    assert [r.identifier for r in middle] == ["id:1", "id:2", "id:3"]


def test_hierarchical_sets(store):
    oai = Oai(store, "full")
    oai.add("id:1", prefixes=["didl"], sets=["genre:poetry"])
    oai.add("id:2", prefixes=["didl"], sets=["genre:novels"])
    oai.add("id:3", prefixes=["didl"], sets=["OpenAccess"])
    assert listed(oai, "didl", set="genre") == [("id:1", False), ("id:2", False)]
    assert listed(oai, "didl", set="genre:poetry") == [("id:1", False)]
    assert oai.sets == {
        "genre": "",
        "genre:poetry": "",
        "genre:novels": "",
        "OpenAccess": "",
    }
    oai.update_set("OpenAccess", "Open access")
    assert oai.sets["OpenAccess"] == "Open access"
    with pytest.raises(ValueError):
        oai.add("id:4", prefixes=["didl"], sets=["a,b"])


def test_delete(store):
    oai = Oai(store, "full", always_delete_in_prefixes=["didl"])
    oai.add("id:1", prefixes=["oai_dc"], sets=["poetry"])
    oai.delete("id:1")
    record = oai.get("id:1")
    assert record.tombstone
    # always_delete_in_prefixes: the delete shows in didl too
    assert record.prefixes == {"oai_dc", "didl"} == record.deleted_prefixes
    assert listed(oai, "didl") == [("id:1", True)]
    assert listed(oai, "oai_dc", set="poetry") == [("id:1", True)]
    # unknown: deleted in always_delete_in_prefixes
    oai.delete("id:unknown")
    assert listed(oai, "didl")[-1] == ("id:unknown", True)
    # added again without its set: still deleted in all its sets, so deleted (as
    # OaiJazz)
    oai.add("id:1", prefixes=["oai_dc"])
    assert oai.get("id:1").tombstone
    # added again with it: no longer deleted in the prefixes and sets added
    oai.add("id:1", prefixes=["oai_dc"], sets=["poetry"])
    assert not oai.get("id:1").tombstone
    assert listed(oai, "oai_dc") == [("id:1", False)]
    assert listed(oai, "didl")[0] == ("id:unknown", True)


def test_delete_unknown_without_prefixes_is_ignored(store):
    oai = Oai(store, "full")
    oai.delete("id:unknown")
    assert oai.get("id:unknown") is None
    with pytest.raises(ValueError):
        oai.delete("id:unknown", sets=["poetry"])


def test_delete_in_prefixes(store):
    oai = Oai(store, "full")
    oai.add("id:1", prefixes=["didl", "oai_openaire"])
    oai.delete_in_prefixes("id:1", ["oai_openaire"])
    assert listed(oai, "oai_openaire") == [("id:1", True)]
    assert listed(oai, "didl") == [("id:1", False)]
    assert not oai.get("id:1").tombstone
    oai.delete_in_prefixes("id:1", ["didl"])
    assert oai.get("id:1").tombstone  # deleted in all its prefixes


def test_delete_in_sets(store):
    oai = Oai(store, "full")
    with pytest.raises(ValueError):
        oai.delete_in_sets("id:1", ["poetry"])
    oai = Oai(store, "discover", delete_in_sets=True)
    oai.add("id:1", prefixes=["didl"], sets=["poetry", "novels"])
    oai.delete_in_sets("id:1", ["poetry"])
    record = oai.get("id:1")
    assert record.is_deleted_for("didl", sets=["poetry"])
    assert not record.is_deleted_for("didl", sets=["novels"])
    assert not record.tombstone
    oai.delete_in_sets("id:1", ["novels"])
    assert oai.get("id:1").tombstone  # deleted in all its sets
    oai.delete_in_sets("id:unknown", ["poetry"])  # ignored
    assert oai.get("id:unknown") is None


def test_repositories_are_separate(store):
    full, discover = Oai(store, "full"), Oai(store, "discover")
    full.add("id:1", prefixes=["didl"])
    discover.add("id:2", prefixes=["didl"])
    assert listed(full, "didl") == [("id:1", False)]
    assert listed(discover, "didl") == [("id:2", False)]


def test_stamps_go_on_after_reopening(tmp_path):
    store = new_store(tmp_path)
    oai = Oai(store, "full")
    oai.add("id:1", prefixes=["didl"])
    last = oai.get("id:1").stamp
    oai._newest_stamp = last + 10**12  # as if the clock went back afterwards

    store = new_store(tmp_path)
    oai = Oai(store, "full")
    assert oai._newest_stamp == last
    oai.add("id:2", prefixes=["didl"])
    assert oai.get("id:2").stamp > last
    assert oai.formats == {"didl": {"schema": "", "namespace": ""}}


def test_in_one_transaction_with_the_application(store):
    oai = Oai(store, "full")
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.create(Document, {"title": "fiets"})
            oai.add("id:1", prefixes=["didl"])
            raise RuntimeError("stop")
    assert oai.get("id:1") is None
    assert listed(oai, "didl") == []


def test_listeners_hear_of_changes_after_the_transaction(store):
    heard = []
    store.on_transaction(lambda changes: heard.append(sorted(changes)))
    oai = Oai(store, "full")
    with store.transaction():
        oai.add("id:1", prefixes=["didl"])
        oai.add("id:2", prefixes=["didl"])
        assert heard == []
    assert len(heard) == 1
    assert len([qid for qid in heard[0] if qid.startswith("OaiRecord:")]) == 2


def test_a_failing_listener_does_not_undo_the_transaction(store, caplog):
    store.on_transaction(lambda changes: 1 / 0)
    oai = Oai(store, "full")
    oai.add("id:1", prefixes=["didl"])
    assert oai.get("id:1") is not None
    assert "failed" in caplog.text
