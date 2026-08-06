from .indexes import Indexes, Commit

from .base import Base
from .field import Field

from sil.indexfield import IndexField


class Obj(Base):
    FIELDS = Base.FIELDS + [Field.str("something")]
    INDEX = [IndexField.unqualified(name="ALL"), IndexField.text(name="something")]

    def index_values(self):
        return dict(something=self.something, ALL=self.something)


def test_indexes(tmp_path):
    indexes = Indexes(tmp_path, [Obj], Commit(immediate=True))

    assert indexes.get("Obj") is not None
    assert indexes.get(Obj) is not None

    obj = Obj()
    assert indexes.get(obj) is not None


def test_add_query_delete(tmp_path):
    indexes = Indexes(tmp_path, [Obj], Commit(immediate=True))
    assert indexes.search_query(Obj, "*") == {"count": 0, "docs": [], "drilldown": {}}

    obj = Obj()
    obj.update(something="tekst")
    indexes.add_record(obj=obj)

    result = indexes.search_query(Obj, "*")
    assert result["count"] == 1
    assert result["docs"][0]["__id__"] == obj.qid

    result = indexes.search_query(Obj, "tekst")
    assert result["count"] == 1
    assert result["docs"][0]["__id__"] == obj.qid

    result = indexes.search_query(Obj, "nothing")
    assert result == {"count": 0, "docs": [], "drilldown": {}}

    indexes.delete_record(obj=obj)
    assert indexes.search_query(Obj, "*") == {"count": 0, "docs": [], "drilldown": {}}
