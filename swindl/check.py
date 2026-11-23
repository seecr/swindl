## begin license ##
#
# "Swindl"(Seecr Web Index and Database Lib) combines sjdbl's files and sil's index
#
# Copyright (C) 2026 Seecr (Seek You Too B.V.) https://seecr.nl
#
# This file is part of "swindl"
#
# "swindl" is licensed under the MIT License; see the LICENSE file.
# SPDX-License-Identifier: MIT
#
## end license ##

"""swindl-check: does the index match the files? Reports, never repairs.

    swindl-check <data dir> <module>:<list of models>
    swindl-check /data/myapp myapp.models:ALL_MODELS

Exit code 0 when all is well, 1 when there are problems (one per line). It only reads:
it does not open a Store (which would finish an interrupted commit), so it can run
next to the application, and after a crash it shows what opening the store will do.
The repair is the application's: open the store (an interrupted commit), or reindex
(`actions/reindex`) for an index that differs from the files."""

import argparse
import importlib
import json
import sys
from pathlib import Path

import tantivy
from sil.indexfield import INT, UNTOKENIZED, IndexField
from sjdbl.base import __ARCHIVED__, __ID__, Base, Proxy

from .store.indexes import PendingLog

ID_FIELD = IndexField.ID_FIELD


class _Files:
    """Reads objects straight from the files (no Store: nothing is changed), and
    remembers the references it saw."""

    def __init__(self, store_dir, models):
        self._store_dir = store_dir
        self._models = {model.__name__: model for model in models}
        self.referenced = {}  # qid -> the qid of an object that refers to it

    def proxy(self, qid):
        self.referenced.setdefault(qid, self._current)
        return Proxy(self, qid)

    def get(self, qid):
        cls, _, uuid = qid.partition(":")
        file = self._store_dir / cls / f"{uuid}.json"
        if cls not in self._models or "/" in uuid or not file.is_file():
            return None
        return self._models[cls].from_storage(self, json.loads(file.read_text()))

    def exists(self, qid):
        cls, _, uuid = qid.partition(":")
        return "/" not in uuid and (self._store_dir / cls / f"{uuid}.json").is_file()

    def read_all(self, model, problems):
        for file in sorted((self._store_dir / model.__name__).glob("*.json")):
            self._current = f"{model.__name__}:{file.stem}"
            try:
                yield model.from_storage(self, json.loads(file.read_text()))
            except ValueError as e:
                problems.append(f"{file}: not readable: {e}")


def check(data_dir, models):
    """The problems found, as lines of text; [] when all is well."""
    data_dir = Path(data_dir)
    store_dir, index_dir = data_dir / "store", data_dir / "index"
    models = [m for m in models if isinstance(m, type) and issubclass(m, Base)]
    problems = []

    if (store_dir / "commit.log").exists():
        problems.append(
            "store/commit.log: a commit was interrupted by a crash; opening the store "
            "finishes it"
        )
    for tmp_file in sorted(store_dir.glob("*/*.tmp")):
        problems.append(
            f"{tmp_file.relative_to(data_dir)}: left by a crash; opening the store "
            "removes it"
        )
    if pending := PendingLog(index_dir / "pending.log").qids():
        problems.append(
            f"index/pending.log: {len(pending)} object(s) not yet (surely) indexed; "
            "opening the store indexes them"
        )

    files = _Files(store_dir, models)
    for model in models:
        objs = list(files.read_all(model, problems))
        if hasattr(model, "INDEX"):
            problems.extend(_check_index(index_dir / model.__name__, model, objs))

    for qid, by in sorted(files.referenced.items()):
        if not files.exists(qid):
            problems.append(f"{by}: refers to {qid}, which does not exist")
    return problems


def _check_index(path, model, objs):
    name = model.__name__
    if not (path / "index" / "meta.json").exists():
        return [f"index/{name}: no index; reindex"] if objs else []
    try:
        index = tantivy.Index.open(str(path / "index"))
    except ValueError as e:
        return [f"index/{name}: cannot be opened ({e}); reindex"]
    searcher = index.searcher()
    in_index = {}
    if searcher.num_docs:
        hits = searcher.search(tantivy.Query.all_query(), limit=searcher.num_docs).hits
        for _, address in hits:
            qid = searcher.doc(address).to_dict()[ID_FIELD][0]
            in_index[qid] = in_index.get(qid, 0) + 1

    problems = []
    in_files = {obj.qid: obj for obj in objs}
    for qid in sorted(set(in_index) - set(in_files)):
        problems.append(f"index/{name}: {qid} is indexed but has no file")
    for qid in sorted(set(in_files) - set(in_index)):
        problems.append(f"index/{name}: {qid} has a file but is not indexed")
    for qid, count in sorted(in_index.items()):
        if count > 1:
            problems.append(f"index/{name}: {qid} is indexed {count} times")

    exact = [
        field
        for field in [IndexField.untokenized(__ARCHIVED__), *model.INDEX]
        if field.field_type in (UNTOKENIZED, INT) and field.name != ID_FIELD
    ]
    schema = index.schema
    for qid in sorted(set(in_files) & set(in_index)):
        obj = in_files[qid]
        values = obj.index_values()
        values[__ID__] = str(obj[__ID__])
        values[__ARCHIVED__] = str(obj[__ARCHIVED__])
        for field in exact:
            value = values.get(field.name)
            for each in (
                [] if value is None else value if isinstance(value, list) else [value]
            ):
                query = tantivy.Query.boolean_query(
                    [
                        (
                            tantivy.Occur.Must,
                            tantivy.Query.term_query(schema, ID_FIELD, qid),
                        ),
                        (
                            tantivy.Occur.Must,
                            tantivy.Query.term_query(
                                schema, field.name, field.term_value(each)
                            ),
                        ),
                    ]
                )
                if searcher.search(query, limit=1).count == 0:
                    problems.append(
                        f"index/{name}: {qid} is indexed with another {field.name} "
                        f"than its file has ({each!r}); reindex"
                    )
    return problems


def load_models(spec):
    module_name, _, attribute = spec.partition(":")
    module = importlib.import_module(module_name)
    return (
        getattr(module, attribute)
        if attribute
        else [
            value
            for value in vars(module).values()
            if isinstance(value, type) and issubclass(value, Base) and value is not Base
        ]
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="swindl-check",
        description="Reports whether a swindl store's index matches its files. "
        "Changes nothing.",
    )
    parser.add_argument("data_dir", type=Path, help="the directory given to Store")
    parser.add_argument(
        "models", help="<module>:<list of models>, or <module> for all models in it"
    )
    args = parser.parse_args(argv)
    sys.path.insert(0, "")
    problems = check(args.data_dir, load_models(args.models))
    for problem in problems:
        print(problem)
    if not problems:
        print("ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
