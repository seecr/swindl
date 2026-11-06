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
