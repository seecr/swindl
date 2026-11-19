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

"""OAI-PMH for swindl: Oai (the OAI administration of a repository, kept in the
application's Store), OaiProvider (answers OAI-PMH requests) and OaiDownloader
(harvests another OAI-PMH repository). See "OAI-PMH" in doc/reference.md."""

from .repository import MODELS, Oai, OaiRecord, OaiRepository

__all__ = ["MODELS", "Oai", "OaiRecord", "OaiRepository"]
