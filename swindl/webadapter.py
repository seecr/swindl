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

from decimal import Decimal


def as_is(value):
    return value


def from_web_method(name, method):
    def wrapped_from_web_method(obj, form):
        value = form.get(name)
        return method(value)

    return wrapped_from_web_method


def to_web_method(method):
    def wrapped_to_web_method(obj, value):
        return method(value)

    return wrapped_to_web_method


class Adapt:
    @classmethod
    def str(cls, name, from_web=None, to_web=None):
        return cls(
            name,
            from_web=from_web_method(name, from_web or str),
            to_web=to_web_method(to_web or str),
        )

    @classmethod
    def int(cls, name, from_web=None, to_web=None):
        return cls(
            name,
            from_web=from_web_method(name, from_web or int),
            to_web=to_web_method(to_web or str),
        )

    @classmethod
    def decimal(cls, name, decimals=2, from_web=None, to_web=None):
        def quantized(v):
            return v.quantize(Decimal(10) ** -decimals)

        return cls(
            name,
            from_web=from_web_method(
                name, from_web or (lambda v: quantized(Decimal(v)))
            ),
            to_web=to_web_method(to_web or (lambda v: str(quantized(v)))),
        )

    @classmethod
    def bool(cls, name):
        def from_web(obj, form):
            return name in form

        return cls(name, from_web=from_web, to_web=to_web_method(str))

    @classmethod
    def method(cls, name, from_web=None, to_web=None):
        from_web = from_web or as_is

        def wrapped_from_web(obj, form):
            value = form.get(name)
            return from_web(value)

        to_web = to_web or as_is

        def wrapped_to_web(obj, value):
            return to_web(value)

        return cls(name, from_web=wrapped_from_web, to_web=wrapped_to_web)

    def __init__(self, name, from_web=None, to_web=None):
        self._name = name
        self._from_web = from_web or as_is
        self._to_web = to_web or as_is

    @property
    def name(self):
        return self._name

    @property
    def to_web(self):
        return self._to_web

    def from_web(self, obj, form):
        return self._from_web(obj, form)


class WebAdapter:
    def __init__(self, obj, adaptations=None):
        self._obj = obj
        self._adaptations = {
            adapt.name: adapt for adapt in getattr(obj, "ADAPTATIONS", [])
        }
        self._add_adaptations(adaptations)

    @classmethod
    def adapt(cls, obj, form, fields, adaptations=None):
        wa = cls(obj, adaptations)
        return wa.from_web(form, fields)

    def original(self, name):
        return getattr(self._obj, name)

    def _add_adaptations(self, adaptations):
        adaptations = adaptations or []
        for adapt in adaptations:
            self._adaptations[adapt.name] = adapt

    def __getattr__(self, key):
        value = getattr(self._obj, key)
        if (adapt := self._adaptations.get(key)) is None:
            return value
        return adapt.to_web(self._obj, value)

    def from_web(self, form, fields, adaptations=None):
        self._add_adaptations(adaptations)
        result = {}
        for field in fields:
            if (adapt := self._adaptations.get(field)) is not None:
                value = adapt.from_web(self._obj, form)
            else:
                value = form.get(field)

            if value is not None:
                result[field] = value
        return result
