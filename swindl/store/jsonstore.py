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
