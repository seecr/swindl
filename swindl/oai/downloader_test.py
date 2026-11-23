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

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlparse

import pytest
from sil.indexfield import IndexField
from sjdbl.field import Field

from ..store import Base
from ..store.indexes import Commit
from ..store.store import Store
from . import MODELS as PROVIDER_MODELS
from .downloader import MODELS, OaiDownloader, OaiDownloadError
from .provider import CLIENT_HEADER, OaiProvider
from .repository import Oai

BASE = "http://provider.example.org/oai"


class Copy(Base):
    FIELDS = Base.FIELDS + [
        Field.str("identifier"),
        Field.str("text"),
        Field.bool("deleted", False),
    ]
    INDEX = Base.INDEX + [IndexField.untokenized("identifier")]

    def index_values(self):
        return {**super().index_values(), "identifier": self.identifier}


@pytest.fixture
def provider_side(tmp_path):
    store = Store(tmp_path / "provider", PROVIDER_MODELS, commit=Commit(immediate=True))
    oai = Oai(store, "document")
    provider = OaiProvider(
        oai,
        metadata=lambda record, prefix: (
            f'<text xmlns="urn:test">{record.identifier}</text>'
        ),
        name="Provider",
        admin_email="beheer@example.org",
        batch_size=2,
        supports_x_wait=True,
    )
    return oai, provider


@pytest.fixture
def consumer(tmp_path):
    return Store(tmp_path / "consumer", MODELS + [Copy], commit=Commit(immediate=True))


def in_process(provider, calls=None):
    """fetch: the provider answers without HTTP."""

    async def fetch(url, headers):
        if calls is not None:
            calls.append((url, dict(headers)))
        response = await provider.handle(
            parse_qsl(urlparse(url).query), BASE, client=headers.get(CLIENT_HEADER)
        )
        return response.status, response.body

    return fetch


def storing(store, seen=None):
    def process(records):
        for record in records:
            if seen is not None:
                seen.append(record.identifier)
            copy = store.find_one(Copy, identifier=record.identifier) or Copy(
                values={"identifier": record.identifier}
            )
            text = "" if record.deleted else record.metadata.text
            copy.update(text=text, deleted=record.deleted)
            store.put(copy)

    return process


def copies(store):
    return sorted((c.identifier, c.text, c.deleted) for c in store.list(Copy))


def downloader(consumer, provider, **kwargs):
    kwargs.setdefault("process", storing(consumer))
    return OaiDownloader(
        consumer,
        "provider",
        BASE,
        metadata_prefix="document",
        fetch=in_process(provider),
        **kwargs,
    )


async def test_harvest_in_parts(provider_side, consumer):
    oai, provider = provider_side
    for nr in range(5):
        oai.add(f"id:{nr}", prefixes=["document"])
    oai.delete("id:4")
    d = downloader(consumer, provider)
    assert not await d.step()  # parts of 2
    assert d.state.resumption_token
    assert not await d.step()
    assert await d.step()  # the last part
    assert copies(consumer) == [
        ("id:0", "id:0", False),
        ("id:1", "id:1", False),
        ("id:2", "id:2", False),
        ("id:3", "id:3", False),
        ("id:4", "", True),
    ]
    assert d.state.records == 5
    assert d.state.resumption_token == ""
    assert d.state.from_  # the next list from when this one began
    assert "from=" in d.request_url()

    oai.add("id:5", prefixes=["document"])
    while not await d.step():
        pass
    assert ("id:5", "id:5", False) in copies(consumer)


async def test_nothing_to_harvest(provider_side, consumer):
    oai, provider = provider_side
    oai.add("id:0", prefixes=["document"])
    d = downloader(consumer, provider)
    d._from = "2999-01-01T00:00:00Z"
    assert await d.step()  # noRecordsMatch: done
    assert copies(consumer) == []


async def test_parser(provider_side, consumer):
    """A parser of one's own, e.g. to drop whitespace between elements."""
    from lxml import etree

    oai, _ = provider_side
    oai.add("id:0", prefixes=["document"])
    provider = OaiProvider(
        oai,
        metadata=lambda record, prefix: '<a xmlns="urn:test">\n  <b>x</b>\n</a>',
        name="Provider",
        admin_email="beheer@example.org",
    )
    for parser, text in [
        (None, "\n  "),
        (etree.XMLParser(remove_blank_text=True, huge_tree=True), None),
    ]:
        seen = []
        d = downloader(
            consumer,
            provider,
            process=lambda records: seen.extend(records),
            parser=parser,
        )
        d.reset()
        await d.step()
        (record,) = seen
        assert record.metadata.text == text


async def test_after_an_error_one_request_without_x_wait(provider_side, consumer):
    """An x-wait request in a quiet repository does not answer, so it would never
    clear an error: after an error the next request is without x-wait."""
    oai, provider = provider_side
    oai.update_format("document", "", "urn:test")  # an empty repository
    d = downloader(consumer, provider, x_wait=True)
    assert "x-wait=True" in d.request_url()
    d._save_error("HTTP 503")
    assert "x-wait" not in d.request_url()
    again = downloader(consumer, provider, x_wait=True)  # also after a restart
    assert "x-wait" not in again.request_url()
    assert await again.step()  # noRecordsMatch: answered at once
    assert again.state.error == ""
    assert "x-wait=True" in again.request_url()


async def test_x_wait_follows_changes(provider_side, consumer):
    oai, provider = provider_side
    oai.add("id:0", prefixes=["document"])
    calls = []
    d = OaiDownloader(
        consumer,
        "provider",
        BASE,
        metadata_prefix="document",
        process=storing(consumer),
        fetch=in_process(provider, calls),
        x_wait=True,
    )
    d.start()
    try:
        for _ in range(100):
            if copies(consumer):
                break
            await asyncio.sleep(0.01)
        assert copies(consumer) == [("id:0", "id:0", False)]
        assert d.state.resumption_token  # x-wait: a token after the last part too
        await asyncio.sleep(0.05)
        assert provider.waiting == {d.state.client}

        await asyncio.to_thread(oai.add, "id:1", prefixes=["document"])
        for _ in range(100):
            if len(copies(consumer)) == 2:
                break
            await asyncio.sleep(0.01)
        assert copies(consumer)[1] == ("id:1", "id:1", False)
    finally:
        await d.stop()
    assert all("x-wait=True" in url for url, _ in calls)
    assert all(headers[CLIENT_HEADER] == d.state.client for _, headers in calls)


async def test_a_failing_part_is_asked_for_again(provider_side, consumer):
    oai, provider = provider_side
    for nr in range(3):
        oai.add(f"id:{nr}", prefixes=["document"])
    seen = []
    store_them = storing(consumer, seen)
    failures = [RuntimeError("once")]

    def process(records):
        store_them(records)
        if failures:
            raise failures.pop()

    d = downloader(consumer, provider, process=process)
    with pytest.raises(RuntimeError):
        await d.step()
    assert copies(consumer) == []  # undone, the position too
    assert d.state.resumption_token == "" and d.state.records == 0
    assert not await d.step()  # the same part again
    assert await d.step()
    assert [c[0] for c in copies(consumer)] == ["id:0", "id:1", "id:2"]
    assert seen == ["id:0", "id:1", "id:0", "id:1", "id:2"]
    assert d.state.records == 3


async def test_goes_on_after_a_restart(provider_side, consumer):
    oai, provider = provider_side
    for nr in range(3):
        oai.add(f"id:{nr}", prefixes=["document"])
    first = downloader(consumer, provider)
    await first.step()
    token, client = first.state.resumption_token, first.state.client

    again = downloader(consumer, provider)
    assert again.state.resumption_token == token
    assert again.state.client == client
    assert f"resumptionToken={token[:5]}" in again.request_url().replace("%7C", "|")
    assert await again.step()
    assert len(copies(consumer)) == 3


async def test_errors(provider_side, consumer):
    oai, provider = provider_side
    d = downloader(consumer, provider)  # no prefix "document" yet
    with pytest.raises(OaiDownloadError, match="cannotDisseminateFormat"):
        await d.step()

    async def fetch(url, headers):
        return 500, b"oops"

    d = OaiDownloader(consumer, "x", BASE, "document", process=None, fetch=fetch)
    with pytest.raises(OaiDownloadError, match="HTTP 500"):
        await d.step()

    async def not_xml(url, headers):
        return 200, b"<html"

    d = OaiDownloader(consumer, "y", BASE, "document", process=None, fetch=not_xml)
    with pytest.raises(OaiDownloadError, match="no XML"):
        await d.step()


async def test_run_saves_the_error_and_tries_again(provider_side, consumer):
    oai, provider = provider_side
    answers = [(500, b"down"), None]

    async def fetch(url, headers):
        answer = answers.pop(0) if answers else None
        if answer is not None:
            return answer
        return await in_process(provider)(url, headers)

    oai.add("id:0", prefixes=["document"])
    d = OaiDownloader(
        consumer,
        "provider",
        BASE,
        "document",
        process=storing(consumer),
        fetch=fetch,
        retry_delay=0.01,
        interval=10,
    )
    task = d.start()
    for _ in range(100):
        if copies(consumer):
            break
        await asyncio.sleep(0.01)
    await d.stop()
    assert task.done()
    assert copies(consumer) == [("id:0", "id:0", False)]
    assert d.state.error == ""  # cleared by the part that worked


async def test_204_asks_again(provider_side, consumer):
    oai, provider = provider_side

    async def fetch(url, headers):
        return 204, b"ended"

    d = OaiDownloader(consumer, "x", BASE, "document", process=None, fetch=fetch)
    assert not await d.step()
    assert d.state.records == 0


def test_request_url(consumer):
    d = OaiDownloader(
        consumer,
        "x",
        "http://example.org/oai?apikey=secret",
        "didl",
        process=None,
        set="genre:zuyd",
        from_="2026-01-01",
        x_wait=True,
    )
    assert d.request_url() == (
        "http://example.org/oai?apikey=secret&verb=ListRecords&metadataPrefix=didl"
        "&set=genre%3Azuyd&from=2026-01-01&x-wait=True"
    )
    d.state.update(resumption_token="mdidl|c5|f|u|s|p")
    assert d.request_url() == (
        "http://example.org/oai?apikey=secret&verb=ListRecords"
        "&resumptionToken=mdidl%7Cc5%7Cf%7Cu%7Cs%7Cp&x-wait=True"
    )
    d.reset()
    assert d.state.resumption_token == "" and d.state.from_ == ""


async def test_over_http(provider_side, consumer):
    oai, provider = provider_side
    for nr in range(3):
        oai.add(f"id:{nr}", prefixes=["document"])
    seen_headers = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen_headers.append(dict(self.headers))
            response = provider.respond(parse_qsl(urlparse(self.path).query), BASE)
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        d = OaiDownloader(
            consumer,
            "http",
            f"http://127.0.0.1:{server.server_port}/oai",
            "document",
            process=storing(consumer),
        )
        while not await d.step():
            pass
    finally:
        server.shutdown()
    assert len(copies(consumer)) == 3
    assert seen_headers[0]["User-Agent"].startswith("swindl OaiDownloader")
