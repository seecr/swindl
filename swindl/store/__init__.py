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

from sil.indexfield import IndexField
from sjdbl.enumerate import EnumerateValue
from sjdbl.field import Field

from .base import Base
from .indexes import Commit, Query
from .store import HasChangedException, QueryParams, Store
