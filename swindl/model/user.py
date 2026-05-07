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

from sdbl.base import Base, Field


class User(Base):
    FIELDS = Base.FIELDS + [
        Field.ID("userbase"),
        Field.str("name"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._userbase_user = None

    @classmethod
    async def create(cls, store, userbase_user):
        result = await store.create(cls, values={"userbase": userbase_user.id})
        result._userbase_user = userbase_user
        return result

    @classmethod
    async def get(cls, store, userbase_user):
        matches = await store.list("User", userbase=userbase_user.id)
        if len(matches) == 1:
            match = matches[0]
            match._userbase_user = userbase_user
            return match

    async def archive(self, store):
        await store.archive("User", self.id)

    @property
    def is_authenticated(self):
        return True

    @property
    def admin(self):
        return self._userbase_user.admin

    @property
    def display_name(self):
        if self.name == "":
            if self._userbase_user is None:
                return "Unknown"
            return self._userbase_user.display_name
        return self.name

    @property
    def data(self):
        return self._userbase_user.data

    @property
    def username(self):
        return self._userbase_user.username

    def set_admin(self, admin=True):
        self._userbase_user.set_admin(admin)
