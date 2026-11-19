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

import asyncio
from datetime import datetime, timezone

import pytest
from lxml import etree

from ..store.indexes import Commit
from ..store.store import Store
from .provider import OaiProvider
from .repository import MODELS, Oai

NOW = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
BASE = "http://example.org/oai"
NS = {"oai": "http://www.openarchives.org/OAI/2.0/", "t": "urn:test"}


def new_store(path, commit=None):
    return Store(path, MODELS, commit=commit or Commit(immediate=True))


@pytest.fixture
def store(tmp_path):
    return new_store(tmp_path)


def provider_for(oai, **kwargs):
    kwargs.setdefault("name", "Test")
    kwargs.setdefault("admin_email", "beheer@example.org")
    return OaiProvider(
        oai,
        metadata=lambda record, prefix: (
            f'<data xmlns="urn:test">{record.identifier} {prefix}</data>'
        ),
        **kwargs,
    )


def ask(provider, **args):
    response = provider.respond(list(args.items()), BASE, now=NOW)
    return etree.fromstring(response.body)


def error(tree):
    found = tree.xpath("/oai:OAI-PMH/oai:error", namespaces=NS)
    return found[0].get("code") if found else None


def xpath(tree, path):
    return tree.xpath(path, namespaces=NS)


def token(tree):
    found = xpath(tree, "//oai:resumptionToken")
    return None if not found else (found[0].text or "")


def test_identify(store):
    oai = Oai(store, "full")
    provider = provider_for(
        oai,
        repository_identifier="example.org",
        descriptions=['<description><x xmlns="urn:test">more</x></description>'],
        watermark="<!-- watermark -->",
    )
    response = provider.respond([("verb", "Identify")], BASE, now=NOW)
    assert response.body.startswith(b'<?xml version="1.0" encoding="UTF-8"?>\n<OAI-PMH')
    assert b"<!-- watermark --><responseDate>2026-11-19T12:00:00Z" in response.body
    tree = etree.fromstring(response.body)
    assert xpath(tree, "//oai:repositoryName/text()") == ["Test"]
    assert xpath(tree, "//oai:baseURL/text()") == [BASE]
    assert xpath(tree, "//oai:deletedRecord/text()") == ["persistent"]
    assert tree.xpath("//*[local-name()='repositoryIdentifier']/text()") == [
        "example.org"
    ]
    assert xpath(tree, "//t:x/text()") == ["more"]
    assert xpath(tree, "//oai:request/@verb") == ["Identify"]
    assert error(ask(provider, verb="Identify", extra="1")) == "badArgument"


def test_verb_errors(store):
    provider = provider_for(Oai(store, "full"))
    assert error(ask(provider)) == "badArgument"
    tree = ask(provider, verb="Nonsense")
    assert error(tree) == "badVerb"
    assert xpath(tree, "//oai:request/@verb") == []  # not echoed
    response = provider.respond(
        [("verb", "Identify"), ("verb", "Identify")], BASE, now=NOW
    )
    assert error(etree.fromstring(response.body)) == "badArgument"


def test_list_records_with_parts_and_tokens(store):
    oai = Oai(store, "full")
    for nr in range(5):
        oai.add(f"id:{nr}", prefixes=["didl"], sets=["genre:zuyd"])
    provider = provider_for(oai, batch_size=2, identifier_prefix="oai:example.org:")

    tree = ask(provider, verb="ListRecords", metadataPrefix="didl")
    identifiers = xpath(tree, "//oai:header/oai:identifier/text()")
    assert identifiers == ["oai:example.org:id:0", "oai:example.org:id:1"]
    assert xpath(tree, "//oai:record[1]/oai:metadata/t:data/text()") == ["id:0 didl"]
    assert xpath(tree, "(//oai:header)[1]/oai:setSpec/text()") == [
        "genre",
        "genre:zuyd",
    ]
    first = token(tree)
    assert first.startswith("mdidl|c") and first.endswith("|f|u|s|p")

    seen = list(identifiers)
    next_token = first
    while next_token:
        tree = ask(provider, verb="ListRecords", resumptionToken=next_token)
        seen += xpath(tree, "//oai:header/oai:identifier/text()")
        next_token = token(tree)
    assert next_token == ""  # the last part: an empty token
    assert seen == [f"oai:example.org:id:{nr}" for nr in range(5)]

    tree = ask(provider, verb="ListIdentifiers", metadataPrefix="didl", set="genre")
    assert len(xpath(tree, "//oai:header")) == 2
    assert xpath(tree, "//oai:metadata") == []


def test_list_errors(store):
    oai = Oai(store, "full")
    oai.add("id:1", prefixes=["didl"])
    provider = provider_for(oai)
    assert error(ask(provider, verb="ListRecords")) == "badArgument"
    assert error(ask(provider, verb="ListRecords", metadataPrefix="mods")) == (
        "cannotDisseminateFormat"
    )
    assert error(ask(provider, verb="ListRecords", metadataPrefix="didl", set="x")) == (
        "noRecordsMatch"
    )
    assert (
        error(ask(provider, verb="ListRecords", resumptionToken="nonsense"))
        == "badResumptionToken"
    )
    tree = ask(provider, verb="ListRecords", metadataPrefix="didl", resumptionToken="x")
    assert error(tree) == "badArgument"
    tree = ask(
        provider, verb="ListRecords", metadataPrefix="didl", **{"x-wait": "True"}
    )
    assert error(tree) == "badArgument"  # not supported here
    for from_, until in [
        ("2026-01-01", "2026-01-01T00:00:00Z"),
        ("2026-02-01", "2026-01-01"),
        ("x", None),
    ]:
        args = {"from": from_} if until is None else {"from": from_, "until": until}
        tree = ask(provider, verb="ListRecords", metadataPrefix="didl", **args)
        assert error(tree) == "badArgument", (from_, until)


def test_from_and_until(store):
    oai = Oai(store, "full")
    oai.add("id:1", prefixes=["didl"])
    provider = provider_for(oai)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for args in [{"from": today}, {"until": today}, {"from": "2000-01-01T00:00:00Z"}]:
        tree = ask(provider, verb="ListIdentifiers", metadataPrefix="didl", **args)
        assert len(xpath(tree, "//oai:header")) == 1, args
    for args in [{"until": "2000-01-01"}, {"from": "2999-01-01"}]:
        tree = ask(provider, verb="ListIdentifiers", metadataPrefix="didl", **args)
        assert error(tree) == "noRecordsMatch", args


def test_deleted_records(store):
    oai = Oai(store, "full")
    oai.add("id:1", prefixes=["didl", "oai_openaire"])
    oai.delete_in_prefixes("id:1", ["oai_openaire"])
    oai.add("id:2", prefixes=["didl"])
    oai.delete("id:2")
    provider = provider_for(oai)
    tree = ask(provider, verb="ListRecords", metadataPrefix="oai_openaire")
    assert xpath(tree, "//oai:header/@status") == ["deleted"]
    assert xpath(tree, "//oai:metadata") == []
    tree = ask(provider, verb="ListRecords", metadataPrefix="didl")
    assert xpath(tree, "//oai:header/@status") == ["deleted"]  # id:2 only
    assert len(xpath(tree, "//oai:metadata")) == 1


def test_get_record_and_formats(store):
    oai = Oai(store, "full")
    oai.add("id:1", prefixes=["didl"])
    oai.update_format("oai_dc", "dc.xsd", "http://purl.org/dc")
    provider = provider_for(
        oai,
        identifier_prefix="oai:x:",
        about=lambda record, prefix: '<provenance xmlns="urn:test"/>',
    )
    tree = ask(
        provider, verb="GetRecord", identifier="oai:x:id:1", metadataPrefix="didl"
    )
    assert xpath(tree, "//oai:metadata/t:data/text()") == ["id:1 didl"]
    assert len(xpath(tree, "//oai:about/t:provenance")) == 1
    assert xpath(tree, "//oai:request/@identifier") == ["oai:x:id:1"]
    tree = ask(provider, verb="GetRecord", identifier="id:1", metadataPrefix="didl")
    assert error(tree) == "idDoesNotExist"
    tree = ask(
        provider, verb="GetRecord", identifier="oai:x:id:1", metadataPrefix="oai_dc"
    )
    assert error(tree) == "cannotDisseminateFormat"
    assert error(ask(provider, verb="GetRecord", identifier="oai:x:id:1")) == (
        "badArgument"
    )

    tree = ask(provider, verb="ListMetadataFormats")
    assert xpath(tree, "//oai:metadataPrefix/text()") == ["didl", "oai_dc"]
    assert xpath(tree, "//oai:schema/text()") == ["dc.xsd"]
    tree = ask(provider, verb="ListMetadataFormats", identifier="oai:x:id:1")
    assert xpath(tree, "//oai:metadataPrefix/text()") == ["didl"]
    tree = ask(provider, verb="ListMetadataFormats", identifier="oai:x:nope")
    assert error(tree) == "idDoesNotExist"


def test_list_sets(store):
    oai = Oai(store, "full")
    provider = provider_for(oai)
    assert error(ask(provider, verb="ListSets")) == "noSetHierarchy"
    oai.add("id:1", prefixes=["didl"], sets=["genre:zuyd"])
    oai.update_set("genre", "Genre")
    tree = ask(provider, verb="ListSets")
    assert xpath(tree, "//oai:setSpec/text()") == ["genre", "genre:zuyd"]
    assert [name.text or "" for name in xpath(tree, "//oai:setName")] == ["Genre", ""]
    assert error(ask(provider, verb="ListSets", resumptionToken="x")) == (
        "badResumptionToken"
    )


def test_deleted_in_a_set_shows_with_delete_in_sets(store):
    oai = Oai(store, "discover", delete_in_sets=True)
    oai.add("id:1", prefixes=["didl"], sets=["zuyd", "avans"])
    oai.delete_in_sets("id:1", ["zuyd"])
    provider = provider_for(oai)
    tree = ask(provider, verb="ListRecords", metadataPrefix="didl", set="zuyd")
    assert xpath(tree, "//oai:header/@status") == ["deleted"]
    assert xpath(tree, "//oai:setSpec[@status='deleted']/text()") == ["zuyd"]
    tree = ask(provider, verb="ListRecords", metadataPrefix="didl", set="avans")
    assert xpath(tree, "//oai:header/@status") == []


# --- x-wait ---


def wait_args(**args):
    return [("verb", "ListRecords"), ("x-wait", "True")] + list(args.items())


async def test_x_wait_needs_a_store_that_finds_changes_at_once(tmp_path):
    oai = Oai(new_store(tmp_path, commit=Commit(timeout=0)), "full")
    with pytest.raises(ValueError):
        provider_for(oai, supports_x_wait=True)
    provider_for(oai)  # without x-wait it is fine


async def test_x_wait_gives_a_token_on_the_last_part_and_waits(store):
    oai = Oai(store, "full")
    oai.add("id:1", prefixes=["didl"])
    provider = provider_for(oai, supports_x_wait=True)

    response = await provider.handle(wait_args(metadataPrefix="didl"), BASE, "c1")
    tree = etree.fromstring(response.body)
    assert xpath(tree, "//oai:identifier/text()") == ["id:1"]
    last = token(tree)
    assert last  # the last part, and still a token

    waiting = asyncio.create_task(
        provider.handle(wait_args(resumptionToken=last), BASE, "c1")
    )
    await asyncio.sleep(0.05)
    assert not waiting.done()
    assert provider.waiting == {"c1"}

    oai.add("id:other", prefixes=["oai_dc"])  # another prefix: still waiting
    await asyncio.sleep(0.05)
    assert not waiting.done()

    await asyncio.to_thread(oai.add, "id:2", prefixes=["didl"])  # in another thread
    response = await asyncio.wait_for(waiting, 2)
    tree = etree.fromstring(response.body)
    assert xpath(tree, "//oai:identifier/text()") == ["id:2"]
    assert token(tree)
    assert provider.waiting == set()


async def test_x_wait_with_a_set(store):
    oai = Oai(store, "full")
    provider = provider_for(oai, supports_x_wait=True)
    waiting = asyncio.create_task(
        provider.handle(wait_args(metadataPrefix="didl", set="zuyd"), BASE, "c1")
    )
    await asyncio.sleep(0.05)
    oai.add("id:1", prefixes=["didl"], sets=["avans"])
    await asyncio.sleep(0.05)
    assert not waiting.done()
    oai.add("id:2", prefixes=["didl"], sets=["zuyd"])
    response = await asyncio.wait_for(waiting, 2)
    assert xpath(etree.fromstring(response.body), "//oai:identifier/text()") == ["id:2"]


async def test_a_new_request_of_the_client_ends_its_waiting_one(store):
    provider = provider_for(Oai(store, "full"), supports_x_wait=True)
    first = asyncio.create_task(
        provider.handle(wait_args(metadataPrefix="didl"), BASE, "c1")
    )
    await asyncio.sleep(0.05)
    second = asyncio.create_task(
        provider.handle(wait_args(metadataPrefix="didl"), BASE, "c1")
    )
    response = await asyncio.wait_for(first, 2)
    assert response.status == 204
    assert b"same OaiClient" in response.body
    await asyncio.sleep(0.05)
    assert provider.waiting == {"c1"} and not second.done()
    second.cancel()


async def test_at_most_max_waiting(store):
    provider = provider_for(Oai(store, "full"), supports_x_wait=True, max_waiting=2)
    tasks = [
        asyncio.create_task(
            provider.handle(wait_args(metadataPrefix="didl"), BASE, f"c{nr}")
        )
        for nr in range(3)
    ]
    await asyncio.sleep(0.1)
    done = [task for task in tasks if task.done()]
    assert len(done) == 1 and done[0].result().status == 204
    assert len(provider.waiting) == 2
    for task in tasks:
        task.cancel()


async def test_without_x_wait_handle_answers_at_once(store):
    provider = provider_for(Oai(store, "full"), supports_x_wait=True)
    response = await provider.handle(
        [("verb", "ListRecords"), ("metadataPrefix", "didl")], BASE
    )
    assert response.error == "cannotDisseminateFormat"
