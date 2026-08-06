from .indexes import Query
from .indexes import Indexes
from .jsonstore import JsonStore
from .base import Base

from .utils import mkdir

from seecr_stdlib import first
import logging

logger = logging.getLogger(__name__)


class HasChangedException(Exception):
    pass


class QueryParams:
    def __init__(self, obj_type, query="*", page=0, size=20, sort=None, filters=None):
        self.query = query
        self.obj_type = obj_type
        self.page = page
        self.size = size
        self.sort = sort
        self.filters = filters or {}


class QueryResult:
    def __init__(self, objs, total, params):
        self.objs = objs
        self.params = params

        self.start = (params.page * params.size) + 1
        self.stop = min((params.page * params.size) + params.size, total)
        self.total = total
        self.pages = Pages(params.page, params.size, total)

    def is_last_page(self):
        return self.pages.last is None or self.params.page == self.pages.last

    @property
    def summary(self):
        if self.total == 0:
            return f"{self.total} resultaten"
        elif self.total == 1:
            return f"{self.total} resultaat"

        return f"{self.start} - {self.stop} van {self.total} resultaten"


class Pages:
    def __init__(self, page, size, total):
        self.first = None if page == 0 else 0
        self.prev = None if page == 0 else page - 1
        self.next = None if (page + 1) * size >= total else page + 1
        self.last = (
            None
            if (page + 1) * size >= total
            else total // size if total % size > 0 else (total // size) - 1
        )


class Store(object):
    def __init__(self, path, models, commit=None):
        self._store = JsonStore(path=mkdir(path / "store"), models=models)
        self._indexes = Indexes(
            path=mkdir(path / "index"), models=models, commit=commit
        )
        self._models = {}
        for model in models:
            if not issubclass(model, Base):
                continue
            model_name = model.__name__

            self._models[model_name] = model

    def enumerator(self, *args, **kwargs):
        return self._store.enumerator(*args, **kwargs)

    def disconnect(self):
        self._indexes.shutdown()

    def create(self, cls, values=None):
        if isinstance(cls, str):
            cls = self._models.get(cls)

        obj = cls(values=values or {})
        self.put(obj)
        return obj

    def put(self, *objs):
        for obj in objs:
            self._store.put(obj)
            self._indexes.add_record(obj)

    def _class(self, cls):
        if isinstance(cls, Base):
            return cls.__class__.__name__
        elif isinstance(cls, str):
            return cls
        else:
            return cls.__name__

    def get(self, qid_or_qrid, include_archived=False, assert_type=None):
        cls, _, identifier = qid_or_qrid.partition(":")
        identifier, _, revision = identifier.partition(":")

        if (record := self._store.get(f"{cls}:{identifier}")) is not None:
            if assert_type is not None and self._class(record) != self._class(
                assert_type
            ):
                raise TypeError(
                    f"Expected {assert_type!r}, got {self._class(record)!r}"
                )

            if revision != "" and record.__rev__ != revision:
                raise HasChangedException()

            if not include_archived and record.__archived__:
                return None

        return record

    def list(self, cls, include_archived=False, **kwargs):
        qp = QueryParams(cls)
        for name, value in kwargs.items():
            qp.filters[name] = value

        if not include_archived:
            qp.filters["__archived__"] = str(False)

        result = self.query(qp)
        while True:
            for obj in result.objs:
                yield obj
            if result.is_last_page():
                break
            qp = result.params
            qp.page = qp.page + 1
            result = self.query(qp)

    def find_one(self, cls, **kwargs):
        qp = QueryParams(cls)
        for name, value in kwargs.items():
            qp.filters[name] = value
        result = self.query(qp)
        return first(result.objs)

    def query(self, query_params):
        objs = []
        obj_type = query_params.obj_type

        if isinstance(query_params.query, str):
            query = Query(query_params.query)
        elif isinstance(query_params.query, Query):
            query = query_params.query
        else:
            raise RuntimeError("Unknown query")

        for name, value in query_params.filters.items():
            if value:
                query.add_term(name, value)

        results = self._indexes.search_by_query(
            obj_type,
            query,
            page=query_params.page + 1,
            limit=query_params.size,
            sort=query_params.sort,
        )
        total = results["count"]
        for doc in results["docs"]:
            if (
                obj := self._store.get(doc["__id__"])  # TODO: , assert_type=obj_type)
            ) is not None:
                objs.append(obj)

        return QueryResult(objs=objs, total=total, params=query_params)

    def delete(self, obj):
        self._store.delete(obj)
        self._indexes.delete_record(obj)

    def archive(self, obj):
        obj.mark_archived()
        self.put(obj)

    def reindex(self, models):
        self._indexes.delete_all()
        for model in models:
            if not hasattr(model, "INDEX"):
                continue
            logger.info(f"Reindexing {model.__name__}")
            records = self._store.list(model)
            for record in records:
                logger.info(f"Reindexing {record.qid}")
                self._indexes.add_record(record)
