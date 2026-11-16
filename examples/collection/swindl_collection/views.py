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

"""The actions: everything the page asks the server to do.

The page (page.j2) has a form #screen with what you are looking at: the search text, the
collection, the facet values you clicked, the sort and the page. The results placeholder
posts it to items_list whenever it changes; items_list answers with the results, the
facets and the address bar url. Other actions don't render the results: they change the
data and say "reload the results" (rehydrate)."""

from urllib.parse import urlencode

from markupsafe import Markup, escape

from swindl.webadapter import FieldError, FormErrors, from_form, to_form

from . import catalog
from .model import CONDITIONS, KINDS, Collection, Item, now

RESULTS = "results"  # the placeholder with the items (page.j2)
FACETS = "facets"  # the facets next to them, hydrated by items_list
COLLECTIONS = "collections"  # the placeholder with your collections
SCREEN_STATE = "screen-state"  # the hidden fields of the #screen form

ITEM_FIELDS = ["title", "maker", "year", "code", "format", "condition", "tags",
               "acquired", "price", "notes"]  # fmt: skip
COLLECTION_FIELDS = ["name", "kind", "description", "public"]

# what the WebAdapter's error codes mean, for people
MESSAGES = {
    "invalid_int": "a whole number",
    "invalid_decimal": "a number, like 12.50",
    "invalid_date": "a date, like 2024-05-31",
    "too_small": "at least %(min)s",
    "too_large": "at most %(max)s",
    "too_long": "at most %(max)s characters",
    "not_allowed": "one of the choices",
    "required": "filled in",
}


def error_texts(errors):
    texts = {}
    for name, error in errors.items():
        text = MESSAGES.get(error.code, error.code)
        try:
            texts[name] = "Should be " + text % error.params
        except (KeyError, TypeError):
            texts[name] = "Should be " + text
    return texts


# --- the screen: what you are looking at, in a form and in the url ---


def screen_from(form):
    """The screen as posted with the #screen form (plus the values of a clicked
    facet, collection or page button)."""
    filters = [tuple(f.split("=", 1)) for f in form.getlist("f") if "=" in f]
    filters = [(field, value) for field, value in filters if field in catalog.FACETS]
    if (add := form.get("add")) and "=" in add:
        field, value = add.split("=", 1)
        if field in catalog.FACETS and (field, value) not in filters:
            filters.append((field, value))
    if (remove := form.get("remove")) and "=" in remove:
        filters = [f for f in filters if f != tuple(remove.split("=", 1))]
    collection = form.get("collection", form.get("c", ""))
    sort = form.get("sort", "relevance")
    try:  # "goto" from a page button, else the page we are on
        page = max(0, int(form.get("goto", form.get("page", 0))))
    except ValueError:
        page = 0
    q = form.get("q", "").strip()
    if (
        "add" in form
        or "remove" in form
        or "collection" in form
        or q != form.get("q_was", q)
        or sort != form.get("sort_was", sort)
    ):
        page = 0  # another selection: back to the first page
    return {
        "q": q,
        "c": collection,
        "f": filters,
        "sort": sort if sort in catalog.SORTS else "relevance",
        "page": page,
    }


def page_url(q="", c="", f=(), sort="relevance", page=0):
    params = [("q", q)] if q else []
    params += [("c", c.split(":", 1)[-1])] if c else []
    params += [("f", f"{field}={value}") for field, value in f]
    params += [("sort", sort)] if sort != "relevance" else []
    params += [("page", page)] if page else []
    return "/" + ("?" + urlencode(params) if params else "")


def render_state(screen):
    """The hidden fields of #screen that keep the collection, facets and page, and the
    search and sort they are for (another search starts at page 1 again)."""
    fields = [("c", screen["c"]), ("page", screen["page"])]
    fields += [("q_was", screen["q"]), ("sort_was", screen["sort"])]
    fields += [("f", f"{field}={value}") for field, value in screen["f"]]
    return Markup(
        "".join(
            f'<input type="hidden" name="{name}" value="{escape(value)}">'
            for name, value in fields
        )
    )


# --- the results ---


async def items_list(request, swl, store, **kwargs):
    """The results, the facets and the url for the screen."""
    async with request.form() as form:
        screen = screen_from(form)
        highlight = form.get("highlight")
        collection_chosen = "collection" in form
    username = request.user.username
    collection = catalog.owned_collection(store, _collection_qid(screen["c"]), username)
    if collection is None:
        screen["c"] = ""
    result = catalog.search(
        store,
        username,
        q=screen["q"],
        collection=collection,
        filters=screen["f"],
        sort=screen["sort"],
        page=screen["page"],
    )
    names = {c.qid: c.name for c in catalog.my_collections(store, username)}
    labels = collection.labels if collection else KINDS["other"]
    html = swl.template("collection/results.j2").render(
        result=result,
        screen=screen,
        collection=collection,
        names=names,
        labels=labels,
        highlight=highlight,
    )
    facets = swl.template("collection/facets.j2").render(
        drilldown=result.drilldown, screen=screen, names=names, labels=labels
    )
    response = (
        swl.success()
        .hydrate(RESULTS, html)
        .hydrate(FACETS, facets)
        .hydrate(SCREEN_STATE, render_state(screen))
        .set_url(page_url(**screen))
    )
    if collection_chosen:
        response.rehydrate(COLLECTIONS)  # to mark the chosen one
    return response


def _collection_qid(value):
    if not value:
        return None
    return value if value.startswith("Collection:") else f"Collection:{value}"


async def collections_list(request, swl, store, **kwargs):
    async with request.form() as form:
        selected = _collection_qid(form.get("c"))
    html = swl.template("collection/collections.j2").render(
        collections=catalog.my_collections(store, request.user.username),
        selected=selected,
        kinds=KINDS,
    )
    return swl.success().hydrate(COLLECTIONS, html)


# --- collections ---


async def collection_new(request, swl, **kwargs):
    return _collection_form(swl, None, values=to_form(Collection(), COLLECTION_FIELDS))


async def collection_edit(request, swl, store, **kwargs):
    async with request.form() as form:
        collection = catalog.owned_collection(
            store, form.get("collection_id"), request.user.username
        )
    if collection is None:
        return swl.fail().message("This collection no longer exists")
    return _collection_form(
        swl, collection, values=to_form(collection, COLLECTION_FIELDS)
    )


def _collection_form(swl, collection, values, errors=None, replace=False):
    html = swl.template("collection/collection_form.j2").render(
        collection=collection, values=values, errors=errors or {}, kinds=KINDS
    )
    if replace:
        return swl.success().hydrate_modal(html)
    return swl.success().open_modal(html, call="collection_focus")


async def collection_save(request, swl, store, **kwargs):
    async with request.form() as form:
        username = request.user.username
        collection_id = form.get("collection_id")
        collection = catalog.owned_collection(store, collection_id, username)
        if collection_id and collection is None:
            return swl.fail().message("This collection no longer exists")
        try:
            values = from_form(Collection, form, COLLECTION_FIELDS, obj=collection)
            if not values.get("name", getattr(collection, "name", "")):
                raise FormErrors({"name": _required()})
        except FormErrors as e:
            return _collection_form(
                swl,
                collection,
                values=to_form(
                    collection or Collection(), COLLECTION_FIELDS, form=form
                ),
                errors=error_texts(e.errors),
                replace=True,
            )
    if collection is None:
        collection = store.create(
            Collection, dict(owner=username, created=now(), **values)
        )
    else:
        collection.update(**values)
        store.put(collection)
    return (
        swl.success()
        .close_modal()
        .rehydrate(COLLECTIONS)
        .rehydrate(RESULTS, context={"collection": collection.qid})
        .toast(f"Saved '{collection.name}'")
    )


def _required():
    return FieldError("required")


async def collection_delete(request, swl, store, **kwargs):
    async with request.form() as form:
        collection = catalog.owned_collection(
            store, form.get("collection_id"), request.user.username
        )
    if collection is None:
        return swl.fail().message("This collection no longer exists")
    count = catalog.delete_collection(store, collection)
    return (
        swl.success()
        .rehydrate(COLLECTIONS)
        .rehydrate(RESULTS, context={"collection": ""})
        .toast(f"Deleted '{collection.name}' and its {count} items")
    )


async def collection_import(request, swl, store, **kwargs):
    async with request.form() as form:
        collection = catalog.owned_collection(
            store, form.get("collection_id"), request.user.username
        )
    if collection is None:
        return swl.fail().message("This collection no longer exists")
    html = swl.template("collection/import_form.j2").render(
        collection=collection, text="", errors=[], columns=catalog.IMPORT_COLUMNS
    )
    return swl.success().open_modal(html)


async def collection_import_save(request, swl, store, **kwargs):
    async with request.form() as form:
        collection = catalog.owned_collection(
            store, form.get("collection_id"), request.user.username
        )
        text = form.get("text", "")
    if collection is None:
        return swl.fail().message("This collection no longer exists")
    count, errors = catalog.import_csv(store, collection, text)
    if errors:
        html = swl.template("collection/import_form.j2").render(
            collection=collection,
            text=text,
            errors=errors[:20],
            more=max(0, len(errors) - 20),
            columns=catalog.IMPORT_COLUMNS,
        )
        return swl.success().hydrate_modal(html)
    return (
        swl.success()
        .close_modal()
        .rehydrate(RESULTS, context={"collection": collection.qid})
        .toast(f"Imported {count} items into '{collection.name}'")
    )


# --- items ---


async def item_new(request, swl, store, **kwargs):
    async with request.form() as form:
        collection = catalog.owned_collection(
            store,
            form.get("collection_id") or _collection_qid(form.get("c")),
            request.user.username,
        )
    collections = catalog.my_collections(store, request.user.username)
    if not collections:
        return swl.fail().message("Make a collection first")
    collection = collection or collections[0]
    return _item_form(
        swl, None, collection, collections, values=to_form(Item(), ITEM_FIELDS)
    )


async def item_edit(request, swl, store, **kwargs):
    async with request.form() as form:
        item = catalog.owned_item(store, form.get("item_id"), request.user.username)
    if item is None:
        return swl.fail().message("This item no longer exists")
    collections = catalog.my_collections(store, request.user.username)
    return _item_form(
        swl, item, item.collection, collections, values=to_form(item, ITEM_FIELDS)
    )


def _item_form(swl, item, collection, collections, values, errors=None, replace=False):
    html = swl.template("collection/item_form.j2").render(
        item=item,
        collection=collection,
        collections=collections,
        labels=collection.labels,
        values=values,
        errors=errors or {},
        conditions=CONDITIONS,
    )
    if replace:
        return swl.success().hydrate_modal(html)
    return swl.success().open_modal(html, call="collection_focus")


async def item_save(request, swl, store, **kwargs):
    username = request.user.username
    async with request.form() as form:
        item_id = form.get("item_id")
        item = catalog.owned_item(store, item_id, username)
        if item_id and item is None:
            return swl.fail().message("This item no longer exists")
        collection = catalog.owned_collection(
            store, form.get("collection_id"), username
        )
        if collection is None:
            return swl.fail().message("This collection no longer exists")
        try:
            values = from_form(Item, form, ITEM_FIELDS, obj=item)
            if not values.get("title"):
                raise FormErrors({"title": _required()})
        except FormErrors as e:
            return _item_form(
                swl,
                item,
                collection,
                catalog.my_collections(store, username),
                values=to_form(item or Item(), ITEM_FIELDS, form=form),
                errors=error_texts(e.errors),
                replace=True,
            )
    if item is None:
        item = catalog.new_item(collection, values)
    else:
        item.update(collection=collection, **values)
    store.put(item)
    return (
        swl.success()
        .close_modal()
        .rehydrate(RESULTS, context={"highlight": item.qid})
        .toast(f"Saved '{item.title}'")
    )


async def item_delete(request, swl, store, **kwargs):
    async with request.form() as form:
        item = catalog.owned_item(store, form.get("item_id"), request.user.username)
    if item is None:
        return swl.fail().message("This item no longer exists")
    store.delete(item)
    return swl.success().rehydrate(RESULTS).toast(f"Deleted '{item.title}'")


async def maker_options(request, swl, store, **kwargs):
    """The <option>s of the maker field's datalist, while typing (item_form.j2)."""
    async with request.form() as form:
        collection = catalog.owned_collection(
            store, form.get("collection_id"), request.user.username
        )
        typed = form.get("maker", "")
    makers = catalog.maker_suggestions(store, collection, typed) if collection else []
    html = Markup("").join(
        Markup('<option value="{}">').format(maker) for maker in makers
    )
    return swl.success().hydrate("maker-options", html)


__actions__ = [
    items_list,
    collections_list,
    collection_new,
    collection_edit,
    collection_save,
    collection_delete,
    collection_import,
    collection_import_save,
    item_new,
    item_edit,
    item_save,
    item_delete,
    maker_options,
]
