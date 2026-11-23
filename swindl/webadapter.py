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

"""From a web form to the values of an object, and back: converting and checking.

Declared once per model, in ADAPTATIONS (a field without an Adapt is text):

    class Person(Base):
        FIELDS = [...]
        ADAPTATIONS = [
            Adapt.date("dob"),
            Adapt.int("age", checks=[at_least(0)]),
            Adapt.str("name", checks=[max_length(100)]),
            Adapt.bool("active"),
        ]

and used in a view:

    fields = ["name", "dob", "active"]
    try:
        person.update(**from_form(Person, form, fields, obj=person))
    except FormErrors as e:
        values = to_form(person, fields, form=form)   # what was typed
        ...render the form again with values and e.errors

The rules, per field in `fields`: not sent is left alone (not in the result), except a
checkbox, which is False then; sent is stripped, and empty becomes None (text: ""); then
converted and checked. Adapt.custom gets the form itself and decides. Errors of all
fields are collected in one FormErrors.
"""

from datetime import date as _date
from decimal import Decimal, InvalidOperation


class FieldError(ValueError):
    """A wrong value: a code (e.g. "too_long") and its params (e.g. {"max": 100}).

    The application translates the code: _(error.code, **error.params).
    """

    def __init__(self, code, **params):
        super().__init__(code, params)
        self.code = code
        self.params = params

    def __repr__(self):
        return f"FieldError({self.code!r}, **{self.params!r})"


class FormErrors(ValueError):
    """The wrong values of a form: errors = {field name: FieldError}."""

    def __init__(self, errors):
        super().__init__(errors)
        self.errors = errors


# checks: functions of the converted value (never None) that raise FieldError


def at_least(n):
    def check(value):
        if value < n:
            raise FieldError("too_small", min=n)

    return check


def at_most(n):
    def check(value):
        if value > n:
            raise FieldError("too_large", max=n)

    return check


def max_length(n):
    def check(value):
        if len(value) > n:
            raise FieldError("too_long", max=n)

    return check


def one_of(values):
    """The value is one of values; taken when called, so pass the current ones."""
    allowed = set(values)

    def check(value):
        if value not in allowed:
            raise FieldError("not_allowed")

    return check


def _quantize(value, decimals):
    return value.quantize(Decimal(10) ** -decimals)


class Adapt:
    """How one field comes from a form (convert) and goes to it (to_web)."""

    def __init__(
        self,
        name,
        convert=str,
        to_web=str,
        checks=None,
        checkbox=False,
        invalid="invalid",
        custom=None,
        empty=None,
    ):
        self.name = name
        self.convert = convert
        self.to_web = to_web
        self.checks = list(checks or [])
        self.checkbox = checkbox
        self.invalid = invalid
        self.custom = custom
        self.empty = empty

    @classmethod
    def str(cls, name, from_web=None, to_web=None, checks=None):
        return cls(name, from_web or str, to_web or str, checks, empty="")

    @classmethod
    def int(cls, name, from_web=None, to_web=None, checks=None):
        return cls(name, from_web or int, to_web or str, checks, invalid="invalid_int")

    @classmethod
    def decimal(cls, name, decimals=2, from_web=None, to_web=None, checks=None):
        def convert(text):
            try:
                value = Decimal(text)
            except InvalidOperation:
                raise ValueError(text)
            if not value.is_finite():
                raise ValueError(text)
            return _quantize(value, decimals)

        return cls(
            name,
            from_web or convert,
            to_web or (lambda value: str(_quantize(value, decimals))),
            checks,
            invalid="invalid_decimal",
        )

    @classmethod
    def date(cls, name, from_web=None, to_web=None, checks=None):
        return cls(
            name,
            from_web or _date.fromisoformat,
            to_web or _date.isoformat,
            checks,
            invalid="invalid_date",
        )

    @classmethod
    def bool(cls, name):
        """A checkbox: in `fields` but not sent (unchecked) is False."""
        return cls(name, convert=None, to_web=bool, checkbox=True)

    @classmethod
    def custom(cls, name, from_web, to_web, checks=None):
        """from_web(obj, form) returns the value, used as is; obj is None when creating.
        to_web(obj, value) returns the text for the form. Either can raise FieldError.
        """
        return cls(name, to_web=to_web, checks=checks, custom=from_web)

    def from_form(self, form, obj):
        """(True, value) for the result, or (False, None) to leave the field alone."""
        if self.custom is not None:
            return True, self._checked(self.custom(obj, form))
        if self.checkbox:
            return True, self.name in form
        if self.name not in form:
            return False, None
        text = form.get(self.name).strip()
        if text == "":
            return True, self.empty
        try:
            value = self.convert(text)
        except FieldError:
            raise
        except (ValueError, TypeError):
            raise FieldError(self.invalid)
        return True, self._checked(value)

    def _checked(self, value):
        if value is not None:
            for check in self.checks:
                check(value)
        return value

    def value_to_form(self, obj, value):
        if self.custom is not None:
            return self.to_web(obj, value)
        if self.checkbox:
            return bool(value)
        return "" if value is None else self.to_web(value)


def _adaptations(model, adaptations):
    result = {adapt.name: adapt for adapt in getattr(model, "ADAPTATIONS", [])}
    result.update((adapt.name, adapt) for adapt in adaptations or [])
    return result


def _adapt(adapts, name):
    return adapts.get(name) or Adapt.str(name)


def from_form(model, form, fields, obj=None, adaptations=None):
    """The values of `fields` from `form`, converted and checked, for
    obj.update(**values) or Model.create(**values). Raises FormErrors with the errors
    of all fields; nothing is returned partially.
    """
    adapts = _adaptations(model, adaptations)
    values, errors = {}, {}
    for name in fields:
        try:
            sent, value = _adapt(adapts, name).from_form(form, obj)
        except FieldError as e:
            errors[name] = e
            continue
        if sent:
            values[name] = value
    if errors:
        raise FormErrors(errors)
    return values


def to_form(obj, fields, form=None, adaptations=None):
    """The values for the inputs of `fields`, as text (a checkbox: a bool).

    With form= (showing a form again after errors): what was typed, for the fields
    that were sent; a checkbox is then whether it was sent.
    """
    adapts = _adaptations(type(obj), adaptations)
    values = {}
    for name in fields:
        adapt = _adapt(adapts, name)
        if form is not None and adapt.checkbox:
            values[name] = name in form
        elif form is not None and name in form:
            values[name] = form.get(name)
        else:
            values[name] = adapt.value_to_form(obj, getattr(obj, name))
    return values
