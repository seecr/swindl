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

"""What the application does with its data, without anything of the web: searching,
deleting a collection with its items, importing. The actions (views.py) call these.

Everything goes through swindl's Store:
  store.query(QueryParams(...))      search, filter, sort, page and count (sil)
  store.get(qid) / store.put(obj)    read and save (sjdbl's files, then the index)
  with store.transaction(): ...      several changes: all of them, or none"""

import csv
import io

from swindl.store.store import QueryParams
from swindl.webadapter import FormErrors, from_form

from .model import Collection, Item, now

PAGE_SIZE = 20

# the drilldown of a search: counts per value, for the facets next to the results
FACETS = ["collection", "maker_exact", "decade", "format", "condition", "tag"]

SORTS = {
    "relevance": None,  # the best matches first (with a query), else the newest
    "recent": [{"field": "created", "reverse": True}],
    "title": ["title_sort"],
    "maker": ["maker_sort", "year"],
    "year": ["year", "title_sort"],
    "year-desc": [{"field": "year", "reverse": True}, "title_sort"],
}


def my_collections(store, username):
    return sorted(store.list(Collection, owner=username), key=lambda c: c.name.lower())


def owned_collection(store, qid, username):
    """The collection with this qid if it is username's, else None. qids come from
    requests: assert_type makes sure it is a Collection, not any object."""
    try:
        collection = store.get(qid, assert_type=Collection) if qid else None
    except (TypeError, ValueError):
        return None
    return collection if collection and collection.owner == username else None


def public_collection(store, qid):
    try:
        collection = store.get(qid, assert_type=Collection)
    except (TypeError, ValueError):
        return None
    return collection if collection and collection.public else None


def owned_item(store, qid, username):
    try:
        item = store.get(qid, assert_type=Item) if qid else None
    except (TypeError, ValueError):
        return None
    return item if item and item.owner == username else None


def search_text(q):
    """The query for what was typed in the search box: all words must match, and the
    last one is a prefix while typing ("blue no" finds "Blue Note"). An empty box finds
    everything; text with query syntax (quotes, field:, OR, ...) is used as it is."""
    q = q.strip()
    if not q:
        return "*"
    words = q.split()
    if all(word.isalnum() for word in words):
        return " ".join(f"+{word}" for word in words) + "*"
    return q


def search(store, owner, q="", collection=None, filters=(), sort="relevance", page=0):
    """One page of owner's items, with the counts per facet value.

    filters: (field, value) pairs from clicked facets; all of them must match."""
    terms = {"owner": owner, "__archived__": "False"}
    if collection is not None:
        terms["collection"] = collection.qid
    for field, value in filters:
        terms.setdefault(field, [])
        if not isinstance(terms[field], list):
            terms[field] = [terms[field]]
        terms[field].append(value)
    if sort not in SORTS:
        sort = "relevance"
    order = SORTS[sort]
    if order is None and not q.strip():
        order = SORTS["recent"]
    return store.query(
        QueryParams(
            Item,
            query=search_text(q),
            filters=terms,
            sort=order,
            page=page,
            size=PAGE_SIZE,
            drilldown=[{"name": name, "count": 12} for name in FACETS],
        )
    )


def maker_suggestions(store, collection, typed):
    """Makers (artists, themes) in collection that match what was typed, most used
    first: a drilldown on a prefix query, so only the owner's own items count."""
    words = ["".join(c for c in word if c.isalnum()) for word in typed.split()]
    if not (words := [word for word in words if word]) or len(typed.strip()) < 2:
        return []
    query = " ".join(f"+maker:{word}" for word in words[:-1]) + f" +maker:{words[-1]}*"
    result = store.query(
        QueryParams(
            Item,
            query=query,
            filters={"owner": collection.owner, "collection": collection.qid},
            size=1,  # only the counts are used
            drilldown=[{"name": "maker_exact", "count": 10}],
        )
    )
    return [value for value, _ in result.drilldown.get("maker_exact", [])]


def delete_collection(store, collection):
    """The collection and all its items, in one transaction: after a crash halfway, they
    are either all there or all gone."""
    items = list(store.list(Item, collection=collection.qid, include_archived=True))
    with store.transaction():
        for item in items:
            store.delete(item)
        store.delete(collection)
    return len(items)


IMPORT_COLUMNS = ["title", "maker", "year", "code", "format", "condition", "tags",
                  "acquired", "price", "notes"]  # fmt: skip


def import_csv(store, collection, text):
    """Adds the rows of a CSV text (with a header row) to collection, all or nothing.

    Every row is checked by the WebAdapter, as a form would be: a wrong value gives an
    error for that row and nothing is imported. Columns may be named by the field
    ("maker") or by the collection's label ("Artist"). Returns (count, errors)."""
    reader = csv.DictReader(io.StringIO(text.strip()))
    if reader.fieldnames is None:
        return 0, ["The text is empty"]
    by_label = {
        collection.labels["maker"].lower(): "maker",
        collection.labels["code"].lower(): "code",
        collection.labels["format"].lower(): "format",
    }
    columns = {}
    for name in reader.fieldnames:
        key = (name or "").strip().lower()
        field = by_label.get(key, key)
        if field in IMPORT_COLUMNS:
            columns[name] = field
    if "title" not in columns.values():
        return 0, ["The first row must name the columns, with at least 'title'"]

    items, errors = [], []
    for nr, row in enumerate(reader, start=2):
        form = {field: (row.get(name) or "") for name, field in columns.items()}
        try:
            values = from_form(Item, form, list(columns.values()))
        except FormErrors as e:
            errors.extend(
                f"Row {nr}, {field}: {error.code}" for field, error in e.errors.items()
            )
            continue
        if not values.get("title"):
            errors.append(f"Row {nr}: no title")
            continue
        items.append(new_item(collection, values))
    if errors:
        return 0, errors
    with store.transaction():
        for item in items:
            store.put(item)
    return len(items), []


def new_item(collection, values):
    return Item.create(
        collection=collection, owner=collection.owner, created=now(), **values
    )


def reindex_if_asked(store, data_dir, models):
    """The explicit reindex step: an empty file <data>/actions/reindex, left by whoever
    upgrades the application when its CHANGELOG says so. Never done otherwise."""
    flag = data_dir / "actions" / "reindex"
    if flag.exists():
        store.reindex(models)
        flag.unlink()
        return True
    return False
