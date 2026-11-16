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

"""The models: collections, and the items in them.

A Collection belongs to one user and holds items of one kind (vinyl records, LEGO sets,
or anything else). Its kind decides the labels of an item's fields: "Artist" and
"Catalogue no." for a record, "Theme" and "Set number" for a LEGO set.

FIELDS (sjdbl) say what is stored; INDEX and index_values (sil) what can be searched,
sorted and counted; ADAPTATIONS (swindl's WebAdapter) how form input becomes values."""

from datetime import datetime, timezone

from sil.indexfield import IndexField
from sjdbl.field import Field

from swindl.store import Base
from swindl.webadapter import Adapt, at_least, at_most, max_length, one_of

KINDS = {
    "vinyl": {
        "label": "Vinyl records",
        "item": "record",
        "maker": "Artist",
        "code": "Catalogue no.",
        "format": "Format",
        "formats": ["LP", "2xLP", "EP", '7"', '10"', '12"', "Box set"],
    },
    "lego": {
        "label": "LEGO sets",
        "item": "set",
        "maker": "Theme",
        "code": "Set number",
        "format": "Pieces",
        "formats": [],
    },
    "other": {
        "label": "Other",
        "item": "item",
        "maker": "Maker",
        "code": "Number",
        "format": "Format",
        "formats": [],
    },
}
CONDITIONS = ["mint", "near mint", "very good", "good", "fair", "poor"]


def _tags(obj, form):
    """ "jazz, blue note,  ,Jazz" -> ["jazz", "blue note"]: trimmed, lowercased, unique.
    Not in the form: as they were."""
    if "tags" not in form:
        return list(obj.tags) if obj is not None else []
    tags = []
    for tag in form.get("tags", "").split(","):
        if (tag := tag.strip().lower()) and tag not in tags:
            tags.append(tag)
    return tags


def _tags_text(obj, value):
    return ", ".join(value or [])


def now():
    return datetime.now(timezone.utc)


class Collection(Base):
    FIELDS = Base.FIELDS + [
        Field.str("owner"),  # a username
        Field.str("name"),
        Field.str("kind", default="vinyl"),
        Field.text("description"),
        Field.bool("public", default=False),
        Field.datetime("created"),
    ]
    INDEX = Base.INDEX + [
        IndexField.untokenized("owner"),
        IndexField.untokenized("public"),
        IndexField.untokenized("name_sort", sortable=True),
    ]
    ADAPTATIONS = [
        Adapt.str("name", checks=[max_length(100)]),
        Adapt.str("kind", checks=[one_of(list(KINDS))]),
        Adapt.bool("public"),
    ]

    def index_values(self):
        values = super().index_values()
        values.update(
            owner=self.owner,
            public=str(self.public),
            name_sort=self.name.lower(),
        )
        return values

    @property
    def labels(self):
        return KINDS.get(self.kind, KINDS["other"])


class Item(Base):
    FIELDS = Base.FIELDS + [
        Field.reference("collection"),
        Field.str("owner"),  # the collection's owner: every search filters on it
        Field.str("title"),
        Field.str("maker"),  # artist, theme, ...
        Field.int("year", default=None),
        Field.str("code"),  # catalogue number, set number, ...
        Field.str("format"),  # LP, 7", ...; for LEGO the number of pieces
        Field.str("condition", default=""),
        Field.json("tags", default=list),
        Field.text("notes"),
        Field.date("acquired"),
        Field.decimal("price"),
        Field.datetime("created"),
    ]
    INDEX = Base.INDEX + [
        # what a search box searches: words from all of these
        IndexField.unqualified("all"),
        IndexField.text("title"),
        IndexField.text("maker"),
        IndexField.untokenized("owner"),
        IndexField.untokenized("collection", drilldown=True),
        IndexField.untokenized("maker_exact", drilldown=True, suggest=True),
        IndexField.untokenized("code", suggest=True),
        IndexField.untokenized("format", drilldown=True),
        IndexField.untokenized("condition", drilldown=True),
        IndexField.untokenized("tag", drilldown=True, suggest=True),
        IndexField.int("decade", drilldown=True),
        IndexField.int("year", sortable=True),
        IndexField.untokenized("title_sort", sortable=True),
        IndexField.untokenized("maker_sort", sortable=True),
        IndexField.untokenized("created", sortable=True),
    ]
    ADAPTATIONS = [
        Adapt.str("title", checks=[max_length(200)]),
        Adapt.str("maker", checks=[max_length(200)]),
        Adapt.int("year", checks=[at_least(1800), at_most(2100)]),
        Adapt.str("code", checks=[max_length(50)]),
        Adapt.str("format", checks=[max_length(50)]),
        Adapt.str("condition", checks=[one_of(["", *CONDITIONS])]),
        Adapt.custom(
            "tags", from_web=lambda obj, form: _tags(obj, form), to_web=_tags_text
        ),
        Adapt.date("acquired"),
        Adapt.decimal("price", checks=[at_least(0)]),
    ]

    def index_values(self):
        values = super().index_values()
        tags = list(self.tags or [])
        values.update(
            all=" ".join(
                str(v)
                for v in [self.title, self.maker, self.code, self.format, *tags]
                if v
            ),
            title=self.title,
            maker=self.maker,
            owner=self.owner,
            collection=self.collection.qid if self.collection else None,
            maker_exact=self.maker or None,
            code=self.code or None,
            format=self.format or None,
            condition=self.condition or None,
            tag=tags,
            decade=self.year // 10 * 10 if self.year else None,
            year=self.year,
            title_sort=self.title.lower(),
            maker_sort=(self.maker or "").lower(),
            created=self.created.isoformat() if self.created else None,
        )
        return values


MODELS = [Collection, Item]
