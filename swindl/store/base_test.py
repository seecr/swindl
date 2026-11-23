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

import pytest
from sjdbl.field import Field

from ..webadapter import Adapt
from . import Base


def test_adapt_for_a_field_that_does_not_exist():
    message = "Person: Adapt for 'dbo', which is not a field"
    with pytest.raises(TypeError, match=message):

        class Person(Base):
            FIELDS = [Field.date("dob")]
            ADAPTATIONS = [Adapt.date("dbo")]


def test_field_adapted_twice():
    with pytest.raises(TypeError, match="Person: 'dob' is adapted twice"):

        class Person(Base):
            FIELDS = [Field.date("dob")]
            ADAPTATIONS = [Adapt.date("dob"), Adapt.str("dob")]


def test_index_and_adaptations():
    class Person(Base):
        FIELDS = [Field.date("dob")]

    assert Person.INDEX == [] and Person.ADAPTATIONS == []


def test_sjdbl_checks_still_apply():
    with pytest.raises(TypeError, match="clashes"):

        class Person(Base):
            FIELDS = [Field.str("qid")]
