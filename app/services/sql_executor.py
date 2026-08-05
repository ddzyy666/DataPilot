from dataclasses import dataclass
from time import perf_counter
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.services.sql_permissions import SQLPermissionPolicy


class SQLExecutionError(RuntimeError):
    def __init__(self, database_error: str, execution_time_ms: float) -> None:
        super().__init__("SQL 执行失败，且已达到自动修复次数限制。")
        self.database_error = database_error
        self.execution_time_ms = execution_time_ms


class SQLQueryTimeoutError(RuntimeError):
    def __init__(self, timeout_seconds: float, execution_time_ms: float) -> None:
        super().__init__(f"SQL 执行超过 {timeout_seconds:g} 秒，查询已被中断。")
        self.execution_time_ms = execution_time_ms


@dataclass(slots=True)
class SQLExecutionResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    execution_time_ms: float


class SQLExecutor:
    def __init__(
        self,
        target_engine: Engine,
        max_rows: int = 200,
        timeout_seconds: float = 5.0,
        permission_policy: SQLPermissionPolicy | None = None,
    ) -> None:
        if max_rows < 1:
            raise ValueError("max_rows 必须大于 0。")
        self.target_engine = target_engine
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds
        self.permission_policy = permission_policy

    def execute(self, sql: str) -> SQLExecutionResult:
        if self.permission_policy is not None:
            self.permission_policy.validate(sql)

        started_at = perf_counter()
        timed_out = False
        sqlite_connection: Any | None = None

        try:
            with self.target_engine.connect() as connection:
                if self.target_engine.dialect.name == "sqlite":
                    connection.exec_driver_sql("PRAGMA query_only = ON")
                    sqlite_connection = connection.connection.driver_connection
                    deadline = started_at + self.timeout_seconds

                    def interrupt_expired_query() -> int:
                        nonlocal timed_out
                        if perf_counter() >= deadline:
                            timed_out = True
                            return 1
                        return 0

                    assert sqlite_connection is not None
                    sqlite_connection.set_progress_handler(interrupt_expired_query, 1000)

                try:
                    result = connection.execute(text(sql))
                    columns = list(result.keys())
                    fetched_rows = result.mappings().fetchmany(self.max_rows + 1)
                finally:
                    if sqlite_connection is not None:
                        sqlite_connection.set_progress_handler(None, 0)
        except SQLAlchemyError as exc:
            elapsed_ms = round((perf_counter() - started_at) * 1000, 2)
            if timed_out:
                raise SQLQueryTimeoutError(self.timeout_seconds, elapsed_ms) from exc
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
