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

from datetime import date
from decimal import Decimal

import pytest
from sjdbl.field import Field

from .store import Base
from .webadapter import (
    Adapt,
    FieldError,
    FormErrors,
    at_least,
    at_most,
    from_form,
    max_length,
    one_of,
    to_form,
)


class Person(Base):
    FIELDS = [
        Field.str("name"),
        Field.str("country"),
        Field.date("dob"),
        Field.int("age"),
        Field.decimal("weight"),
        Field.bool("active", default=False),
    ]
    ADAPTATIONS = [
        Adapt.str("name", checks=[max_length(10)]),
        Adapt.date("dob"),
        Adapt.int("age", checks=[at_least(0), at_most(150)]),
        Adapt.decimal("weight", decimals=2),
        Adapt.bool("active"),
    ]


FIELDS = ["name", "country", "dob", "age", "weight", "active"]


def person():
    return Person.create(
        name="John",
        country="NL",
        dob=date(1955, 5, 15),
        age=70,
        weight=Decimal("80.50"),
        active=True,
    )


def errors(form, fields=FIELDS, **kwargs):
    with pytest.raises(FormErrors) as e:
        from_form(Person, form, fields, **kwargs)
    return {name: (err.code, err.params) for name, err in e.value.errors.items()}


def test_all_types():
    form = dict(
        name=" Jane ",
        country="BE",
        dob="2000-01-02",
        age=" 26",
        weight="61.257",
        active="on",
    )
    assert from_form(Person, form, FIELDS) == {
        "name": "Jane",
        "country": "BE",
        "dob": date(2000, 1, 2),
        "age": 26,
        "weight": Decimal("61.26"),
        "active": True,
    }


def test_not_in_fields_is_never_touched():
    form = dict(name="Jane", age="26", active="on")
    assert from_form(Person, form, ["age"]) == {"age": 26}


def test_not_sent_is_left_alone():
    # no 'None' text for country, no False for a checkbox that is not in fields
    assert from_form(Person, dict(name="Jane"), ["name", "country", "dob", "age"]) == {
        "name": "Jane"
    }


def test_checkbox_in_fields_not_sent_is_false():
    assert from_form(Person, dict(), ["active"]) == {"active": False}
    assert from_form(Person, dict(active="on"), ["active"]) == {"active": True}


def test_empty_is_none_text_is_empty():
    form = dict(dob="", age=" ", weight="", name="", country="  ")
    assert from_form(Person, form, FIELDS) == {
        "dob": None,
        "age": None,
        "weight": None,
        "name": "",
        "country": "",
        "active": False,
    }


def test_invalid_values_per_field():
    form = dict(dob="15-05-1955", age="old", weight="NaN")
    assert errors(form) == {
        "dob": ("invalid_date", {}),
        "age": ("invalid_int", {}),
        "weight": ("invalid_decimal", {}),
    }


def test_errors_of_all_fields_nothing_partial():
    form = dict(name="Jane", age="old", dob="nope")
    assert set(errors(form)) == {"age", "dob"}


def test_checks():
    assert errors(dict(name="x" * 11, age="151"), ["name", "age"]) == {
        "name": ("too_long", {"max": 10}),
        "age": ("too_large", {"max": 150}),
    }
    assert errors(dict(age="-1"), ["age"]) == {"age": ("too_small", {"min": 0})}
    assert from_form(Person, dict(age=""), ["age"]) == {"age": None}  # not checked


def test_one_of_with_current_values():
    products = ["NL", "BE"]
    adaptations = [Adapt.str("country", checks=[one_of(products)])]
    assert from_form(Person, dict(country="BE"), ["country"], adaptations=adaptations)
    assert errors(dict(country="DE"), ["country"], adaptations=adaptations) == {
        "country": ("not_allowed", {})
    }


def test_own_check():
    def not_on_sunday(value):
        if value.weekday() == 6:
            raise FieldError("sunday")

    adaptations = [Adapt.date("dob", checks=[not_on_sunday])]
    assert errors(dict(dob="2026-11-08"), ["dob"], adaptations=adaptations) == {
        "dob": ("sunday", {})
    }


def test_own_conversion():
    adaptations = [
        Adapt.decimal("weight", from_web=lambda t: Decimal(t.replace(",", "."))),
        Adapt.str("name", from_web=str.upper),
    ]
    form = dict(weight="3,5", name="jane")
    assert from_form(Person, form, ["weight", "name"], adaptations=adaptations) == {
        "weight": Decimal("3.5"),
        "name": "JANE",
    }
    assert from_form(Person, dict(name=""), ["name"], adaptations=adaptations) == {
        "name": ""
    }


def full_name(obj, form):
    last = form.get("last") or (obj.name.split()[-1] if obj else "")
    if not form.get("first"):
        raise FieldError("required")
    return f"{form['first']} {last}".strip()


FULL_NAME = Adapt.custom(
    "name", from_web=full_name, to_web=lambda obj, value: value.upper()
)


def test_custom_gets_obj_and_form():
    p = Person.create(name="John Doe")
    form = dict(first="Jane")
    assert from_form(Person, form, ["name"], obj=p, adaptations=[FULL_NAME]) == {
        "name": "Jane Doe"
    }
    assert to_form(p, ["name"], adaptations=[FULL_NAME]) == {"name": "JOHN DOE"}
    assert errors(dict(), ["name"], obj=p, adaptations=[FULL_NAME]) == {
        "name": ("required", {})
    }


def test_custom_when_creating():
    form = dict(first="Jane", last="Roe")
    assert from_form(Person, form, ["name"], adaptations=[FULL_NAME]) == {
        "name": "Jane Roe"
    }


def test_custom_result_used_as_is():
    adapt = Adapt.custom("country", lambda obj, form: None, lambda obj, value: value)
    assert from_form(Person, dict(), ["country"], adaptations=[adapt]) == {
        "country": None
    }


def test_per_form_adaptations_override_the_model():
    adaptations = [Adapt.str("age")]
    assert from_form(Person, dict(age="old"), ["age"], adaptations=adaptations) == {
        "age": "old"
    }


def test_to_form():
    assert to_form(person(), FIELDS) == {
        "name": "John",
        "country": "NL",
        "dob": "1955-05-15",
        "age": "70",
        "weight": "80.50",
        "active": True,
    }


def test_to_form_none_is_empty():
    p = Person.create(name=None, country=None, dob=None, age=None, active=False)
    assert to_form(p, FIELDS) == {
        "name": "",
        "country": "",
        "dob": "",
        "age": "",
        "weight": "",
        "active": False,
    }


def test_to_form_with_typed_values():
    form = dict(name="Jane", age="old")
    assert to_form(person(), FIELDS, form=form) == {
        "name": "Jane",
        "country": "NL",
        "dob": "1955-05-15",
        "age": "old",
        "weight": "80.50",
        "active": False,
    }
    form = dict(active="on")
    assert to_form(person(), ["active"], form=form) == {"active": True}


def test_starlette_like_form():
    class FormData:
        def __init__(self, items):
            self._items = items

        def get(self, name, default=None):
            values = [v for k, v in self._items if k == name]
            return values[-1] if values else default

        def getlist(self, name):
            return [v for k, v in self._items if k == name]

        def __contains__(self, name):
            return any(k == name for k, _ in self._items)

    tags = Adapt.custom(
        "country",
        from_web=lambda obj, form: ",".join(form.getlist("country")),
        to_web=lambda obj, value: value.split(","),
    )
    form = FormData([("country", "NL"), ("country", "BE"), ("age", "3")])
    assert from_form(Person, form, ["country", "age"], adaptations=[tags]) == {
        "country": "NL,BE",
        "age": 3,
    }
