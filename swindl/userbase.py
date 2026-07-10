## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines swl, sil and sdbl
#
# Copyright (C) 2024-2026 Seecr (Seek You Too B.V.) https://seecr.nl
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

from swl.userbase import Userbase as _Userbase

from swindl.model import User
import argon2


class Userbase(_Userbase):
    def __init__(self, store, *args, **kwargs):
        self._userclass = kwargs.get("userclass", User)
        super().__init__(*args, **kwargs)
        self._store = store

    @property
    def userclass(self):
        return self._userclass

    async def create(self, username, password, admin=False, force=False):
        user = await super().create(username, password, admin=admin, force=force)
        if user is not None:
            db_user = await self._userclass.create(self._store, user)
            return db_user

    async def get(self, username):
        user = await super().get(username)
        if user is not None:
            db_user = await self._userclass.get(self._store, user)
            return db_user

    async def put(self, user):
        return await super().put(user._userbase_user)

    async def delete(self, username):
        user = await self.get(username)
        if user is not None:
            success = await super().delete(username)
            if success:
                await user.archive(self._store)
            return success
        return False

    async def setup(self, skip_admin_check=False):
        if not skip_admin_check:
            await self.ensure_admin()
        for user_d in await self.all_users():
            db_user = await self.get(user_d["username"])
            if db_user is not None:
                continue
            base_user = await super().get(user_d["username"])
            await self._userclass.create(self._store, base_user)

    @classmethod
    def for_testing(cls, *args, **kwargs):
        return cls(
            *args,
            _hasher=argon2.PasswordHasher.from_parameters(argon2.profiles.CHEAPEST),
            **kwargs
        )
