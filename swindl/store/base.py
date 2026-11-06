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

from sjdbl.base import Base as JsonBase


class Base(JsonBase):
    """sjdbl's Base with what swindl adds: INDEX (the index fields, see Indexes) and
    ADAPTATIONS (how fields come from a web form, see swindl.webadapter).

    Checked when a model class is defined: every Adapt names a field in FIELDS, and no
    field is adapted twice.
    """

    INDEX = []
    ADAPTATIONS = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        field_names = {field.name for field in cls.FIELDS}
        seen = set()
        for adapt in cls.ADAPTATIONS:
            if adapt.name not in field_names:
                raise TypeError(
                    f"{cls.__name__}: Adapt for {adapt.name!r}, which is not a field"
                )
            if adapt.name in seen:
                raise TypeError(f"{cls.__name__}: {adapt.name!r} is adapted twice")
            seen.add(adapt.name)
