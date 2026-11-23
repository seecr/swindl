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

"""Demo data for the demo user: a few records and LEGO sets, so there is something to
search. Added once, when the application starts without any users."""

from .catalog import new_item
from .model import Collection, now

RECORDS = [
    # title, artist, year, catalogue no., format, tags
    ("Kind of Blue", "Miles Davis", 1959, "CL 1355", "LP", "jazz, modal"),
    ("Blue Train", "John Coltrane", 1958, "BLP 1577", "LP",
     "jazz, hard bop, blue note"),
    ("A Love Supreme", "John Coltrane", 1965, "A-77", "LP", "jazz, spiritual"),
    ("Giant Steps", "John Coltrane", 1960, "", "LP", "jazz, hard bop"),
    ("Moanin'", "Art Blakey & The Jazz Messengers", 1958, "", "LP",
     "jazz, hard bop, blue note"),
    ("Song for My Father", "Horace Silver", 1965, "", "LP", "jazz, blue note"),
    ("Abbey Road", "The Beatles", 1969, "PCS 7088", "LP", "rock, pop"),
    ("Revolver", "The Beatles", 1966, "", "LP", "rock, pop"),
    ("Rumours", "Fleetwood Mac", 1977, "BSK 3010", "LP", "rock"),
    ("The Dark Side of the Moon", "Pink Floyd", 1973, "", "LP", "rock, progressive"),
    ("Wish You Were Here", "Pink Floyd", 1975, "", "LP", "rock, progressive"),
    ("Blue", "Joni Mitchell", 1971, "", "LP", "folk, singer-songwriter"),
    ("Pet Sounds", "The Beach Boys", 1966, "", "LP", "pop"),
    ("What's Going On", "Marvin Gaye", 1971, "", "LP", "soul"),
    ("Songs in the Key of Life", "Stevie Wonder", 1976, "", "2xLP", "soul, funk"),
    ("Exodus", "Bob Marley & The Wailers", 1977, "", "LP", "reggae"),
    ("Remain in Light", "Talking Heads", 1980, "", "LP", "new wave, funk"),
    ("Unknown Pleasures", "Joy Division", 1979, "", "LP", "post-punk"),
    ("London Calling", "The Clash", 1979, "", "2xLP", "punk, rock"),
    ("Blue Monday", "New Order", 1983, "", '12"', "electronic, new wave"),
    ("Heroes", "David Bowie", 1977, "", "LP", "rock"),
    ("Low", "David Bowie", 1977, "", "LP", "rock, electronic"),
    ("Autobahn", "Kraftwerk", 1974, "", "LP", "electronic"),
    ("Blue Lines", "Massive Attack", 1991, "", "LP", "trip hop"),
    ("Paranoid", "Black Sabbath", 1970, "", "LP", "metal, rock"),
]  # fmt: skip

SETS = [
    # title, theme, year, set number
    ("Galaxy Explorer", "Space", 1979, "928"),
    ("Galaxy Explorer", "Icons", 2022, "10497"),
    ("King's Castle", "Castle", 1984, "6080"),
    ("Black Knight's Castle", "Castle", 1992, "6086"),
    ("Black Seas Barracuda", "Pirates", 1989, "6285"),
    ("Millennium Falcon", "Star Wars", 2007, "10179"),
    ("Tree House", "Ideas", 2019, "21318"),
    ("Colosseum", "Creator Expert", 2020, "10276"),
    ("Titanic", "Icons", 2021, "10294"),
]


def add(store, username):
    with store.transaction():
        records = Collection.create(
            owner=username,
            name="My records",
            kind="vinyl",
            description="The records on the shelf in the living room.",
            public=True,
            created=now(),
        )
        lego = Collection.create(
            owner=username, name="LEGO", kind="lego", public=False, created=now()
        )
        store.put(records, lego)
        for title, artist, year, code, format, tags in RECORDS:
            store.put(
                new_item(
                    records,
                    dict(
                        title=title,
                        maker=artist,
                        year=year,
                        code=code,
                        format=format,
                        condition="very good",
                        tags=[tag.strip() for tag in tags.split(",")],
                    ),
                )
            )
        for title, theme, year, number in SETS:
            store.put(
                new_item(lego, dict(title=title, maker=theme, year=year, code=number))
            )
