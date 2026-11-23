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

"""Harvesting another OAI-PMH repository into the application's Store, as meresco's
OaiDownloadProcessor and PeriodicDownload did: part after part with ListRecords, each
part given to process(records) in a store transaction together with the new position.
So a part is stored with the position after it, or neither (after a crash or an error
the same part comes again; process must not mind getting a record again).

    downloader = OaiDownloader(store, "conversion", url, metadata_prefix="document",
                               process=store_records, x_wait=True)
    task = downloader.start()       # an asyncio task; downloader.stop() ends it

With x_wait the repository holds the request until there is something new (swindl's
OaiProvider, or meresco's, with x-wait), so new records come in at once. Without it, a
finished list is asked for again after interval seconds, from the responseDate of the
request that began it."""

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from lxml import etree
from sjdbl.field import Field

from .. import VERSION
from ..store import Base
from .provider import CLIENT_HEADER

logger = logging.getLogger(__name__)

OAI = "http://www.openarchives.org/OAI/2.0/"
NAMESPACES = {"oai": OAI}
USER_AGENT = f"swindl OaiDownloader {VERSION}"
TIMEOUT = 10 * 60  # seconds; an x-wait request is simply asked again after it


class OaiDownloadState(Base):
    """Where a downloader is: the resumption token to go on with, or the from of the
    next list; its client identifier (for x-wait); what happened last."""

    FIELDS = Base.FIELDS + [
        Field.str("name"),
        Field.str("resumption_token"),
        Field.str("from_"),
        Field.str("list_start"),  # responseDate of the first part of this list
        Field.str("client"),
        Field.int("records"),
        Field.str("last_request"),
        Field.str("error"),
    ]


MODELS = [OaiDownloadState]


@dataclass
class Record:
    """A record of a ListRecords part: header values and the elements (lxml)."""

    identifier: str
    datestamp: str
    deleted: bool
    sets: list = field(default_factory=list)
    metadata: object = None  # the element inside <metadata>, or None
    about: list = field(default_factory=list)  # the elements inside <about>s
    element: object = None  # the <record>


class OaiDownloadError(Exception):
    pass


def fetch_with_urllib(url, headers, timeout=TIMEOUT):
    """(status, body) of a GET; HTTP errors as their status. Runs in a thread."""
    try:
        with urlopen(Request(url, headers=headers), timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as e:
        return e.code, e.read()


class OaiDownloader:
    def __init__(
        self,
        store,
        name,
        url,
        metadata_prefix,
        process,
        set=None,
        from_=None,
        x_wait=False,
        interval=60,
        retry_delay=30,
        headers=None,
        fetch=None,
        parser=None,
    ):
        """process(records): store what the records mean; called in a transaction
        of store. fetch(url, headers) -> (status, body): the HTTP GET, in a thread
        (default urllib); for tests an async function may be given. parser: the
        lxml XMLParser for the responses (e.g. huge_tree=True for very large
        records)."""
        self._store = store
        self.name = name
        self._url = urlparse(url)
        self._base_args = parse_qsl(self._url.query)
        self._prefix = metadata_prefix
        self._set = set
        self._from = from_
        self._process = process
        self._x_wait = x_wait
        # after an error the next request is without x-wait: it answers at once, so
        # the error is cleared (an x-wait request in a quiet repository never answers)
        self._after_error = bool(self._load_state_error(store, name))
        self._interval = interval
        self._retry_delay = retry_delay
        self._headers = {"User-Agent": USER_AGENT, **(headers or {})}
        self._fetch = fetch or fetch_with_urllib
        self._parser = parser
        self._task = None
        self.state = self._load_state()

    # --- running ---

    def start(self):
        self._task = asyncio.create_task(self.run())
        return self._task

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def run(self):
        while True:
            try:
                finished = await self.step()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception(f"OAI download {self.name}: {e}")
                self._save_error(repr(e))
                await asyncio.sleep(self._retry_delay)
                continue
            if finished:
                await asyncio.sleep(self._interval)

    async def step(self):
        """One request and its part. True when the list is done (not with x-wait,
        which waits on the repository's side)."""
        url = self.request_url()
        status, body = await self._get(url)
        if status == 204:
            return False  # an x-wait request ended by the repository: ask again
        if status != 200:
            raise OaiDownloadError(f"{url}: HTTP {status}")
        try:
            tree = etree.parse(BytesIO(body), self._parser)
        except etree.XMLSyntaxError as e:
            raise OaiDownloadError(f"{url}: no XML: {e}") from e
        response_date = _first(tree, "/oai:OAI-PMH/oai:responseDate/text()") or ""
        error = _first(tree, "/oai:OAI-PMH/oai:error")
        if error is not None:
            if error.get("code") != "noRecordsMatch":
                raise OaiDownloadError(
                    f"{url}: {error.get('code')}: {(error.text or '').strip()}"
                )
            self._save(records=[], token="", response_date=response_date)
            return True
        records = [
            _record(element)
            for element in tree.xpath(
                "/oai:OAI-PMH/oai:ListRecords/oai:record", namespaces=NAMESPACES
            )
        ]
        token = _first(tree, "/oai:OAI-PMH/oai:ListRecords/oai:resumptionToken/text()")
        self._save(records=records, token=token or "", response_date=response_date)
        return not token

    def request_url(self):
        if self.state.resumption_token:
            args = [("resumptionToken", self.state.resumption_token)]
        else:
            args = [("metadataPrefix", self._prefix)]
            if self._set:
                args.append(("set", self._set))
            if from_ := (self.state.from_ or self._from):
                args.append(("from", from_))
        if self._waits():
            args.append(("x-wait", "True"))
        query = urlencode(self._base_args + [("verb", "ListRecords")] + args)
        return urlunparse(self._url._replace(query=query))

    def reset(self):
        """Harvest everything again: forget the position (an explicit step)."""
        with self._store.transaction():
            self.state.update(
                resumption_token="", from_="", list_start="", records=0, error=""
            )
            self._store.put(self.state)

    # --- internal ---

    async def _get(self, url):
        headers = dict(self._headers)
        if self._waits():
            headers[CLIENT_HEADER] = self.state.client
        if asyncio.iscoroutinefunction(self._fetch):
            return await self._fetch(url, headers)
        return await asyncio.to_thread(self._fetch, url, headers)

    def _save(self, records, token, response_date):
        """The part's records and the position after it, in one transaction."""
        list_start = self.state.list_start
        if not self.state.resumption_token:  # the first part of a list
            list_start = response_date
        changes = dict(
            resumption_token=token,
            list_start=list_start,
            records=self.state.records + len(records),
            last_request=_now(),
            error="",
        )
        if not token:  # the list is done: the next one from when it began
            changes.update(from_=list_start, list_start="")
        try:
            with self._store.transaction():
                if records:
                    self._process(records)
                self.state.update(**changes)
                self._store.put(self.state)
            self._after_error = False
        except BaseException:
            # the transaction is undone; so is the position (in memory too): the
            # same part is asked for again
            self.state = self._load_state()
            raise

    def _waits(self):
        return self._x_wait and not self._after_error

    @staticmethod
    def _load_state_error(store, name):
        state_id = hashlib.sha256(name.encode()).hexdigest()[:40]
        state = store.get(f"OaiDownloadState:{state_id}")
        return state.error if state is not None else ""

    def _save_error(self, message):
        self._after_error = True
        try:
            with self._store.transaction():
                self.state.update(error=message, last_request=_now())
                self._store.put(self.state)
        except Exception:
            logger.exception(f"OAI download {self.name}: saving the error failed")

    def _load_state(self):
        state_id = hashlib.sha256(self.name.encode()).hexdigest()[:40]
        state = self._store.get(f"OaiDownloadState:{state_id}")
        if state is None:
            state = OaiDownloadState.from_storage(
                self._store, {"meta": {"__id__": state_id}, "data": {}}
            )
            state.update(name=self.name, client=str(uuid.uuid4()))
            self._store.put(state)
        return state


def _first(node, path):
    result = node.xpath(path, namespaces=NAMESPACES)
    return result[0] if result else None


def _record(element):
    header = element.find(f"{{{OAI}}}header")
    metadata = element.find(f"{{{OAI}}}metadata")
    return Record(
        identifier=(_first(header, "oai:identifier/text()") or "").strip(),
        datestamp=(_first(header, "oai:datestamp/text()") or "").strip(),
        deleted=header.get("status") == "deleted",
        sets=[
            s.strip() for s in header.xpath("oai:setSpec/text()", namespaces=NAMESPACES)
        ],
        metadata=None if metadata is None or len(metadata) == 0 else metadata[0],
        about=[
            child for about in element.findall(f"{{{OAI}}}about") for child in about
        ],
        element=element,
    )


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
