## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines swl, sil and sdbl
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
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

import json

from .base import Base, Proxy
from .utils import mkdir

import logging

logger = logging.getLogger(__name__)


class Enumerator:
    def __init__(self, path, start=0):
        self._path = path
        if not self._path.exists():
            self._write_value(start)

    def increment(self):
        value = int(self._path.read_text())
        self._write_value(value + 1)
        return value

    def _write_value(self, value):
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(str(value))
        tmp_path.rename(self._path)


class EnumerateValue:
    def __init__(self, name, start=0):
        self.name = name
        self.start = start


class JsonStore:
    def __init__(self, path, models):
        self._path = path
        self._models = {}
        self._enumerators = {}

        for model in models:
            if not issubclass(model, Base):
                continue
            model_name = model.__name__

            self._models[model_name] = model
            (self._path / model_name).mkdir(parents=True, exist_ok=True)

            if hasattr(model, "ENUMERATORS"):
                for enumerate_value in model.ENUMERATORS:
                    name = enumerate_value.name
                    enumerator = Enumerator(
                        self._path / model_name / f"{name}.enumerator",
                        start=enumerate_value.start,
                    )

                    if model_name not in self._enumerators:
                        self._enumerators[model_name] = {}
                    self._enumerators[model_name][name] = enumerator

    def enumerator(self, model, name):
        return self._enumerators.get(model.__name__, {}).get(name)

    def _file_for_qid(self, qid):
        cls, uuid = qid.split(":", 1)
        return self._path / cls / f"{uuid}.json"

    def put(self, *objs):
        for obj in objs:
            file = self._file_for_qid(obj.qid)
            with file.open("w") as fp:
                fp.write(json.dumps(obj.to_storage()))

    def get(self, qid):
        if (file := self._file_for_qid(qid)).exists():
            cls, _ = qid.split(":", 1)
            return self._from_file(self._models[cls], file)

    def delete(self, obj):
        if (file := self._file_for_qid(self._qid(obj))).exists():
            file.unlink()

    def list(self, cls):
        model_name = cls.__name__
        model = self._models[model_name]
        for file in (self._path / model_name).glob("*.json"):
            yield self._from_file(model, file)

    def _from_file(self, model, file):
        with file.open() as fp:
            values = json.loads(fp.read())
            return model.from_storage(self, values)

    def proxy(self, qid):
        return Proxy(self, qid)

    def _qid(self, obj):
        if isinstance(obj, Base):
            return obj.qid
        elif isinstance(obj, str):
            cls, _ = obj.split(":", 1)
            if cls in self._models:
                return obj
        raise ValueError(f"No qid found for: {obj}")
