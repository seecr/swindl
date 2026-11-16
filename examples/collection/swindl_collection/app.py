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

"""Wires the application together: the store, SWL, the pages and the login."""

from contextlib import asynccontextmanager
from pathlib import Path

from seecr_stdlib.config import Config
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse
from starlette.routing import Mount, Route
from swl import SWL, StaticFiles, static_dir
from swl.session import SessionAuthBackend, SessionSecretKey
from swl.userbase import Userbase
from swl.views import account

from swindl.store.indexes import Commit
from swindl.store.store import Store

from . import catalog, demo, views
from .model import KINDS, MODELS

__all__ = ["create_app", "DEMO_USER", "DEMO_PASSWORD"]

here = Path(__file__).parent

DEMO_USER = "demo"
DEMO_PASSWORD = "demo-password"


async def page(request, swl, store, **kwargs):
    """The page, for "/" with the screen in its query parameters (views.page_url): the
    results placeholder loads itself with them."""
    params = request.query_params
    screen = views.screen_from(
        _Form(
            q=params.get("q", ""),
            c=params.get("c", ""),
            f=params.getlist("f"),
            sort=params.get("sort", "relevance"),
            page=params.get("page", "0"),
        )
    )
    return swl.template_response(
        request,
        "collection/page.j2",
        {
            "title": "Collection",
            "body_class": "",
            "user": request.user,
            "screen": screen,
            "state_html": views.render_state(screen),
            "sorts": SORT_LABELS,
        },
    )


SORT_LABELS = {
    "relevance": "Best match",
    "recent": "Recently added",
    "title": "Title",
    "maker": "Artist / maker",
    "year": "Year, oldest first",
    "year-desc": "Year, newest first",
}


class _Form(dict):
    """Query parameters in the shape of a posted form (getlist for "f")."""

    def getlist(self, name):
        value = self.get(name, [])
        return value if isinstance(value, list) else [value]


async def public_page(request, swl, store, **kwargs):
    """A collection for everyone to see, if its owner made it public. No login, and
    plain links instead of actions: it is a page to share."""
    qid = f"Collection:{request.path_params['collection_id']}"
    collection = catalog.public_collection(store, qid)
    if collection is None:
        return HTMLResponse("Not found", status_code=404)
    q = request.query_params.get("q", "")
    try:
        page_nr = max(0, int(request.query_params.get("page", 0)))
    except ValueError:
        page_nr = 0
    result = catalog.search(
        store, collection.owner, q=q, collection=collection, sort="maker", page=page_nr
    )
    return swl.template_response(
        request,
        "collection/public.j2",
        {
            "title": collection.name,
            "body_class": "",
            "collection": collection,
            "labels": collection.labels,
            "result": result,
            "q": q,
        },
    )


async def login_page(request, swl, **kwargs):
    return swl.template_response(
        request,
        "collection/login.j2",
        {
            "title": "Log in - Collection",
            "body_class": "",
            "next": request.session.get("next", "/"),
            "demo_user": DEMO_USER,
            "demo_password": DEMO_PASSWORD,
        },
    )


def _closing(store):
    @asynccontextmanager
    async def lifespan(app):
        yield
        store.disconnect()  # commits and closes the indexes

    return lifespan


def create_app(data_dir, userbase=None, demo_data=True):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    if userbase is None:
        userbase = Userbase(data_dir / "users")
    new = not userbase.all_users()
    if new:
        userbase.create(DEMO_USER, DEMO_PASSWORD, admin=True)

    # Commit(immediate=True): a save is searchable at once ("do I have this?" right
    # after adding it). Fine for an application that is mostly read; with many writes
    # the default Commit() (a timer, every 5 seconds) is faster.
    store = Store(data_dir / "data", MODELS, commit=Commit(immediate=True))
    if catalog.reindex_if_asked(store, data_dir, MODELS):
        print("Reindexed: the actions/reindex file was there")
    if new and demo_data:
        demo.add(store, DEMO_USER)

    swl = SWL(
        config=Config({"ui": {"framework": "swl"}}), templates=[here / "templates"]
    )
    swl.register_modules(account, views)  # account: login, users and password dialogs
    swl.register_action_kwargs(userbase=userbase, store=store)
    swl.add_template_globals(KINDS=KINDS, VERSION=swl.SWL_VERSION)

    app = Starlette(
        routes=[
            swl.action_route,
            Route("/", swl.endpoint(page, redirect="/login")),
            Route("/c/{collection_id}", swl.endpoint(public_page, authenticated=False)),
            Route("/login", swl.endpoint(login_page, authenticated=False)),
            Route("/logout", swl.endpoint(account.logout, authenticated=False)),
            Mount("/static", StaticFiles(directory=static_dir), name="static"),
            Mount("/app", StaticFiles(directory=here / "static"), name="app"),
        ],
        middleware=[
            Middleware(
                SessionMiddleware,
                secret_key=SessionSecretKey(data_dir / "session.key").key,
            ),
            Middleware(
                AuthenticationMiddleware, backend=SessionAuthBackend(userbase=userbase)
            ),
        ],
        lifespan=_closing(store),
    )
    app.state.swl = swl
    app.state.store = store
    return app
