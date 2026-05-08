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

from .webadapter import Adapt, WebAdapter


def test_convert_to_web():
    class Person:
        ADAPTATIONS = [Adapt.str("name", from_web=str.upper, to_web=str.lower)]

        def __init__(self, name):
            self.name = name

    p = Person(name="JOHN DOE")

    assert p.name == "JOHN DOE"
    wa = WebAdapter(p)

    assert wa.name == "john doe"


def test_convert_from_web():
    class Person:
        ADAPTATIONS = [
            Adapt.str("name", from_web=str.upper, to_web=str.lower),
            Adapt.int("age"),
        ]

        def __init__(self, name, age, location):
            self.name = name
            self.age = age
            self.location = location

    p = Person(name="John Doe", age=42, location="home")
    assert p.name == "John Doe"
    assert p.age == 42
    assert p.location == "home"

    wa = WebAdapter(p)
    form = dict(name="JoHn DoE", age="69", location="office")
    assert wa.from_web(form, ["name", "age", "location"]) == {
        "name": "JOHN DOE",
        "age": 69,
        "location": "office",
    }

    assert WebAdapter.adapt(p, form, ["name", "age", "location"]) == {
        "name": "JOHN DOE",
        "age": 69,
        "location": "office",
    }


def test_convert_boolean_from_web():
    class Person:
        ADAPTATIONS = [
            Adapt.bool("is_green"),
        ]

        def __init__(self, is_green):
            self.is_green = is_green

    p = Person(is_green=False)
    assert p.is_green is False

    wa = WebAdapter(p)
    assert wa.is_green == "False"

    form = dict(is_green="on")
    assert wa.from_web(form, ["is_green"]) == {"is_green": True}

    form = dict()
    assert wa.from_web(form, ["is_green"]) == {"is_green": False}


def test_additional_adaptations_from_web():
    class Person:
        ADAPTATIONS = [
            Adapt.str("name", from_web=str.upper, to_web=str.lower),
        ]

        def __init__(self, name):
            self.name = name

    wa = WebAdapter(Person(name="John Doe"))

    form = dict(name="Jane Doe")
    assert wa.from_web(
        form, ["name"], adaptations=[Adapt.method("name", from_web=str.swapcase)]
    ) == {"name": "jANE dOE"}


def test_additional_adaptations_to_web():
    class Person:
        ADAPTATIONS = [
            Adapt.str("name", from_web=str.upper, to_web=str.lower),
        ]

        def __init__(self, name):
            self.name = name

    wa = WebAdapter(
        Person(name="John Doe"), adaptations=[Adapt.method("name", to_web=str.swapcase)]
    )
    assert wa.name == "jOHN dOE"
