import plyvel
from typing import Iterable
from zavod.logs import get_logger
from nomenklatura.statement import Statement

from opensanctions import settings
from opensanctions.core.dataset import Dataset
from opensanctions.core.statements import all_statements
from opensanctions.core.db import engine_read

log = get_logger(__name__)


class TimeStampIndex(object):
    def __init__(self, dataset: Dataset) -> None:
        path = settings.DATA_PATH / "timestamps" / dataset.name
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = plyvel.DB(path.as_posix(), create_if_missing=True)

    def index(self, statements: Iterable[Statement]) -> None:
        log.info("Building timestamp index...")
        batch = self.db.write_batch()
        idx = 0
        for idx, stmt in enumerate(statements):
            if stmt.first_seen is not None:
                batch.put(stmt.id.encode("utf-8"), stmt.first_seen.encode("utf-8"))
        batch.write()
        log.info("Index ready.", count=idx)

    @classmethod
    def build(cls, dataset: Dataset, dry_run: bool = False) -> "TimeStampIndex":
        index = cls(dataset)
        if not dry_run:
        with engine_read() as conn:
            statements = all_statements(conn, dataset, external=True)
            index.index(statements)
        return index

    def get(self, id: str) -> str:
        first_seen = self.db.get(id.encode("utf-8"))
        if first_seen is not None:
            return first_seen.decode("utf-8")
        return settings.RUN_TIME_ISO

    def __repr__(self) -> str:
        return f"<TimeStampIndex({self.db.name!r})>"
