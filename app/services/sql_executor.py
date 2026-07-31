from dataclasses import dataclass
from time import perf_counter
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError


class SQLExecutionError(RuntimeError):
    def __init__(self, database_error: str, execution_time_ms: float) -> None:
        super().__init__("SQL 执行失败，且已达到自动修复次数限制。")
        self.database_error = database_error
        self.execution_time_ms = execution_time_ms


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
            elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
            database_error = f"{exc.__class__.__name__}: {exc}"
            raise SQLExecutionError(database_error, elapsed_ms) from exc

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
