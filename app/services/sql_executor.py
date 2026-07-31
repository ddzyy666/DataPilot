from dataclasses import dataclass
from time import perf_counter
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError


class SQLExecutionError(RuntimeError):
    pass


@dataclass(slots=True)
class SQLExecutionResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    execution_time_ms: float


class SQLExecutor:
    def __init__(self, target_engine: Engine, max_rows: int = 200) -> None:
        if max_rows < 1:
            raise ValueError("max_rows 必须大于 0。")
        self.target_engine = target_engine
        self.max_rows = max_rows

    def execute(self, sql: str) -> SQLExecutionResult:
        started_at = perf_counter()

        try:
            with self.target_engine.connect() as connection:
                if self.target_engine.dialect.name == "sqlite":
                    connection.exec_driver_sql("PRAGMA query_only = ON")

                result = connection.execute(text(sql))
                columns = list(result.keys())
                fetched_rows = result.mappings().fetchmany(self.max_rows + 1)
        except SQLAlchemyError as exc:
            raise SQLExecutionError(f"SQL 执行失败: {exc.__class__.__name__}") from exc

        truncated = len(fetched_rows) > self.max_rows
        visible_rows = fetched_rows[: self.max_rows]
        rows = [dict(row) for row in visible_rows]

        return SQLExecutionResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            execution_time_ms=round((perf_counter() - started_at) * 1000, 2),
        )
