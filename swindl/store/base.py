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
