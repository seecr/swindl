## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines swl, sil and sdbl
#
# Copyright (C) 2024-2025 Seecr (Seek You Too B.V.) https://seecr.nl
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

from sdbl.store import Store
from .userbase import Userbase
from swindl.model import ALL_MODELS


@pytest.fixture
async def environment(tmp_path):
    store = Store(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
    )
    await store.setup(models=ALL_MODELS)
    userbase = Userbase(store, tmp_path)
    await userbase.setup(skip_admin_check=True)
    return store, userbase, tmp_path


async def test_create_user(environment):
    store, userbase, _ = environment

    all_users = await userbase.all_users()
    assert len(all_users) == 0
    stored_users = await store.list(userbase.userclass)
    assert len(stored_users) == 0

    u = await userbase.create(username="username", password="secret")
    assert u is not None

    all_users = await userbase.all_users()
    assert len(all_users) == 1
    stored_users = await store.list(userbase.userclass)
    assert len(stored_users) == 1

    u = await userbase.get("username")
    assert u.is_authenticated is True
    assert u.admin is False
    assert u.display_name == "username"


async def test_update_user(environment):
    store, userbase, _ = environment

    await userbase.create(username="username", password="secret")

    u = await userbase.get("username")
    assert u.display_name == "username"
    assert u.username == "username"

    u.update(name="Slim Shady")
    await store.update(u)

    u = await userbase.get("username")
    assert u.is_authenticated is True
    assert u.admin is False
    assert u.display_name == "Slim Shady"
    assert u.username == "username"


async def test_delete_user(environment):
    store, userbase, _ = environment

    await userbase.create(username="slim", password="shady")
    all_users = await userbase.all_users()
    assert len(all_users) == 1
    stored_users = await store.list(userbase.userclass)
    assert len(stored_users) == 1

    await userbase.delete(username="slim")
    all_users = await userbase.all_users()
    assert len(all_users) == 0
    stored_users = await store.list("User")
    assert len(stored_users) == 0


async def test_database_removed(environment):
    store, userbase, path = environment

    await userbase.create(username="slim", password="shady")
    all_users = await userbase.all_users()
    assert len(all_users) == 1

    second_path = path / "second"
    second_path.mkdir()
    users2_path = second_path / "users"
    users2_path.mkdir()
    users2_path.joinpath("slim.json").write_text(
        path.joinpath("users/slim.json").read_text()
    )
    store2 = Store(
        database_url=f"sqlite+aiosqlite:///{second_path}/test.db",
    )
    await store2.setup(models=ALL_MODELS)
    userbase2 = Userbase(store2, second_path)
    await userbase2.setup(skip_admin_check=True)

    all_users = await userbase2.all_users()
    assert len(all_users) == 1
    slim = await userbase2.get("slim")
    assert slim is not None


async def test_admin(environment, capsys):
    store, userbase, path = environment
    all_users = await userbase.all_users()
    assert len(all_users) == 0

    await userbase.setup()

    all_users = await userbase.all_users()
    assert len(all_users) == 1

    user = await userbase.get("admin")

    assert user is not None
    assert user.admin is True
    assert "Admin password:" in capsys.readouterr().out
