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

"""OAI-PMH for swindl: Oai (the OAI administration of a repository, kept in the
application's Store), OaiProvider (answers OAI-PMH requests) and OaiDownloader
(harvests another OAI-PMH repository). See "OAI-PMH" in doc/reference.md."""

from .downloader import MODELS as DOWNLOADER_MODELS
from .downloader import OaiDownloader, OaiDownloadState, Record
from .provider import OaiProvider, OaiResponse
from .repository import MODELS, Oai, OaiRecord, OaiRepository

__all__ = [
    "DOWNLOADER_MODELS",
    "MODELS",
    "Oai",
    "OaiDownloader",
    "OaiDownloadState",
    "OaiProvider",
    "OaiRecord",
    "OaiRepository",
    "OaiResponse",
    "Record",
]
