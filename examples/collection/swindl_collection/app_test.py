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

"""Tests for the example: post to the action urls, check the responses (swl.test_utils)
and what is in the store."""

import re

import pytest
from starlette.testclient import TestClient
from swindl_collection import catalog
from swindl_collection.app import DEMO_PASSWORD, DEMO_USER, create_app
from swindl_collection.model import Collection, Item
from swl.test_utils import assert_fail, assert_success
from swl.userbase import Userbase


@pytest.fixture
def client(tmp_path):
    userbase = Userbase.for_testing(tmp_path / "users")  # fast password hashing
    with TestClient(create_app(tmp_path, userbase=userbase)) as client:
        login(client)
        yield client


def action(client, name):
    return client.app.state.swl.register(name)


def login(client, username=DEMO_USER, password=DEMO_PASSWORD):
    response = client.post(
        action(client, "login"), data={"username": username, "password": password}
    )
    assert_success(response)


def partials(response):
    return dict(
        re.findall(
            r'<hx-partial hx-target="#([^"]+)" hx-swap="innerHTML">(.*?)</hx-partial>',
            response.text,
            re.S,
        )
    )


def store(client):
    return client.app.state.store


def collection_named(client, name):
    return store(client).find_one(Collection, owner=DEMO_USER, name_sort=name.lower())


def search(client, **data):
    response = client.post(action(client, "items_list"), data=data)
    assert_success(response)
    return partials(response)


def test_the_page_and_the_demo_data(client):
    assert client.get("/").status_code == 200
    html = search(client)
    assert "34 items" in html["results"]
    assert "John Coltrane" in html["facets"]


def test_do_i_have_it(client):
    html = search(client, q="kind of bl")  # the last word is a prefix while typing
    assert "You have 1</strong>" in html["results"]
    assert "Kind of Blue" in html["results"]
    html = search(client, q="kind of purple")
    assert "Not in your collection" in html["results"]
    html = search(client, q="10179")  # a set number
    assert "Millennium Falcon" in html["results"]


def test_facets_filter_and_count(client):
    html = search(client, add="maker_exact=John Coltrane")
    assert "3 items" in html["results"]
    assert "Blue Train" in html["results"]
    assert 'value="maker_exact=John Coltrane"' in html["screen-state"]
    html = search(client, f="maker_exact=John Coltrane", add="decade=1960")
    assert "2 items" in html["results"]
    html = search(client, f=["maker_exact=John Coltrane", "decade=1960"],
                  remove="decade=1960")  # fmt: skip
    assert "3 items" in html["results"]


def test_a_collection_and_the_url(client):
    records = collection_named(client, "My records")
    response = client.post(
        action(client, "items_list"),
        data={"collection": records.qid, "q": "blue", "sort": "year"},
    )
    html = partials(response)
    assert "Kind of Blue" in html["results"] and "Galaxy" not in html["results"]
    url = response.headers["HX-Replace-Url"]
    assert url == f"/?q=blue&c={records.id}&sort=year"
    assert client.get(url).status_code == 200


def test_add_an_item_with_errors_then_right(client):
    records = collection_named(client, "My records")
    data = {
        "collection_id": records.qid,
        "title": "Court and Spark",
        "maker": "Joni Mitchell",
        "year": "nineteen",
        "price": "-3",
        "tags": "Folk, folk, 70s",
    }
    response = client.post(action(client, "item_save"), data=data)
    html = partials(response)["modal-content"]
    assert "Should be a whole number" in html
    assert "Should be at least 0" in html
    assert 'value="nineteen"' in html  # what was typed is shown again

    data.update(year="1974", price="12.50")
    assert_success(client.post(action(client, "item_save"), data=data))
    item = store(client).find_one(Item, owner=DEMO_USER, title_sort="court and spark")
    assert item.year == 1974 and str(item.price) == "12.50"
    assert item.tags == ["folk", "70s"]
    assert "You have 2</strong>" in search(client, q="joni")["results"]


def test_edit_keeps_what_the_form_does_not_send(client):
    item = store(client).find_one(Item, owner=DEMO_USER, title_sort="kind of blue")
    data = {"item_id": item.qid, "collection_id": item.collection.qid,
            "title": "Kind of Blue (mono)"}  # fmt: skip
    assert_success(client.post(action(client, "item_save"), data=data))
    again = store(client).get(item.qid)
    assert again.title == "Kind of Blue (mono)"
    assert again.year == 1959 and again.tags == ["jazz", "modal"]


def test_maker_suggestions(client):
    records = collection_named(client, "My records")
    response = client.post(
        action(client, "maker_options"),
        data={"collection_id": records.qid, "maker": "john c"},
    )
    assert partials(response)["maker-options"] == '<option value="John Coltrane">'


def test_delete_a_collection_with_its_items(client):
    lego = collection_named(client, "LEGO")
    response = client.post(
        action(client, "collection_delete"), data={"collection_id": lego.qid}
    )
    assert_success(response)
    assert store(client).get(lego.qid) is None
    assert "25 items" in search(client)["results"]


def test_import_is_all_or_nothing(client):
    records = collection_named(client, "My records")
    bad = "title,Artist,year\nSpace Oddity,David Bowie,1969\nNo Year,Someone,soon\n"
    response = client.post(
        action(client, "collection_import_save"),
        data={"collection_id": records.qid, "text": bad},
    )
    assert "Row 3, year: invalid_int" in partials(response)["modal-content"]
    assert "Not in your collection" in search(client, q="space oddity")["results"]

    good = bad.replace("soon", "2001")
    response = client.post(
        action(client, "collection_import_save"),
        data={"collection_id": records.qid, "text": good},
    )
    assert_success(response)
    assert "You have 1</strong>" in search(client, q="space oddity")["results"]


def test_someone_elses_things_are_out_of_reach(client, tmp_path):
    store(client).create(
        Collection, dict(owner="other", name="Secret", kind="vinyl", public=False)
    )
    secret = store(client).find_one(Collection, owner="other")
    response = client.post(
        action(client, "collection_delete"), data={"collection_id": secret.qid}
    )
    assert_fail(response, "This collection no longer exists")
    response = client.post(
        action(client, "items_list"), data={"collection": secret.qid}
    )
    assert "34 items" in partials(response)["results"]  # all of your own instead
    assert client.get(f"/c/{secret.id}").status_code == 404


def test_public_page(client):
    records = collection_named(client, "My records")
    client.get("/logout")
    response = client.get(f"/c/{records.id}?q=coltrane")
    assert response.status_code == 200
    assert "Blue Train" in response.text and "3 records" in response.text


def test_reindex_on_request(tmp_path):
    userbase = Userbase.for_testing(tmp_path / "users")
    with TestClient(create_app(tmp_path, userbase=userbase)):
        pass
    (tmp_path / "actions").mkdir()
    (tmp_path / "actions" / "reindex").touch()
    with TestClient(create_app(tmp_path, userbase=userbase)) as client:
        assert not (tmp_path / "actions" / "reindex").exists()
        login(client)
        assert "34 items" in search(client)["results"]


def test_catalog_search_text():
    assert catalog.search_text("") == "*"
    assert catalog.search_text("blue no") == "+blue +no*"
    assert catalog.search_text('"blue note"') == '"blue note"'
