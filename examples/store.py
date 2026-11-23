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

"""The Store: objects in sjdbl's JSON files, searchable through sil's index.

Every put goes to both; a get comes from the files, a query asks the index which
objects match and then reads those from the files. Run it:

    PYTHONPATH=. python examples/store.py
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from sil.indexfield import IndexField
from sjdbl.field import Field

from swindl.store import Base, Commit, HasChangedException, Query, QueryParams, Store


class Book(Base):
    FIELDS = Base.FIELDS + [
        Field.str("title"),
        Field.str("genre"),
        Field.int("year"),
        Field.str("note"),  # stored, not indexed
    ]

    # What the index knows of a Book (__id__ and __archived__ are always there).
    INDEX = Base.INDEX + [
        IndexField.unqualified("all"),  # searched by a query without field name
        IndexField.text("title"),
        IndexField.untokenized("genre", drilldown=True),
        IndexField.int("year", sortable=True),
    ]

    # The values for those index fields; called at every put.
    def index_values(self):
        values = super().index_values()
        values.update(
            all=f"{self.title} {self.genre}",
            title=self.title,
            genre=self.genre,
            year=self.year,
        )
        return values


def main(path):
    # Commit(immediate=True): every change is searchable at once (tests, examples).
    # The default commits within 5 seconds, which is much faster for many puts.
    store = Store(path, [Book], commit=Commit(immediate=True))

    for title, genre, year in [
        ("The Hobbit", "fantasy", 1937),
        ("Dune", "sf", 1965),
        ("The Lord of the Rings", "fantasy", 1954),
        ("Neuromancer", "sf", 1984),
    ]:
        store.create(Book, dict(title=title, genre=genre, year=year))

    # Searching: a query (sil/tantivy syntax), filters (exact terms), sort, paging
    # and drilldown (counts per value).
    result = store.query(
        QueryParams(
            "Book",
            query="*",
            filters={"genre": "fantasy"},
            sort=[{"field": "year", "reverse": True}],
            size=10,
            drilldown=[{"name": "genre"}],
        )
    )
    print("fantasy, newest first:", [b.title for b in result.objs])
    print("total:", result.total, "| drilldown:", result.drilldown)

    def titles(**kwargs):
        return [b.title for b in store.query(QueryParams("Book", **kwargs)).objs]

    print("query 'title:dune':", titles(query="title:dune"))
    print("query 'sf' (unqualified):", titles(query="sf", sort="year"))

    q = Query("lord")
    q.add_term("genre", "fantasy")  # what filters do: all of query and terms
    print("Query + term:", titles(query=q))

    # Shortcuts: list (all pages, not archived), find_one, find_by_field.
    print("list sf:", [b.title for b in store.list(Book, genre="sf")])
    dune = store.find_one(Book, title="dune")
    print("find_one:", dune.title, dune.qid)

    # Changing: update, then put. A put whose indexed values did not change (note)
    # does not touch the index.
    dune.update(note="read it again")
    store.put(dune)

    # Revisions: a qrid names a revision; get with an old one raises.
    old_qrid = dune.qrid
    dune.update(year=1966)
    store.put(dune)
    try:
        store.get(old_qrid)
    except HasChangedException:
        print("get(old qrid): HasChangedException")

    # Archive: gone from get and list, unless asked for.
    store.archive(dune)
    print("after archive:", store.get(dune.qid), [b.title for b in store.list(Book)])
    print("include_archived:", store.get(dune.qid, include_archived=True).title)

    paged = store.query(QueryParams("Book", size=2, sort="year"))
    # query does not leave out archived objects (list does): add the filter yourself.
    print(f"paging: {paged.start}-{paged.stop} of {paged.total} (archived Dune too)")
    print(f"pages: next {paged.pages.next}, last {paged.pages.last}")
    active = {"__archived__": "False"}
    print("without archived:", titles(sort="year", filters=active))

    store.delete(dune)
    store.disconnect()


if __name__ == "__main__":
    with TemporaryDirectory() as tmp:
        main(Path(tmp))
