## begin license ##
#
# "WWFT Frontend" is the portal for an organisation to comply with WWFT regulations
#
# All rights reserved.
#
# Copyright (C) 2024-2025 Seecr (Seek You Too B.V.) http://seecr.nl
#
# This file is part of "WWFT Frontend"
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
