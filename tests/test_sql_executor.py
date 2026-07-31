import pytest
from sqlalchemy import create_engine, text

from app.services.sql_executor import SQLExecutionError, SQLExecutor


def test_executor_returns_columns_rows_and_truncation() -> None:
    test_engine = create_engine("sqlite://")
    with test_engine.begin() as connection:
        connection.execute(text("CREATE TABLE metrics (id INTEGER, value TEXT)"))
        connection.execute(
            text("INSERT INTO metrics (id, value) VALUES (1, 'a'), (2, 'b'), (3, 'c')")
        )

    result = SQLExecutor(test_engine, max_rows=2).execute(
        "SELECT id, value FROM metrics ORDER BY id"
    )

    assert result.columns == ["id", "value"]
    assert result.rows == [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}]
    assert result.row_count == 2
    assert result.truncated is True
    assert result.execution_time_ms >= 0


def test_executor_uses_readonly_sqlite_connection() -> None:
    test_engine = create_engine("sqlite://")
    executor = SQLExecutor(test_engine)

    with pytest.raises(SQLExecutionError) as error:
        executor.execute("CREATE TABLE forbidden_table (id INTEGER)")

    assert "OperationalError" in error.value.database_error
    assert error.value.execution_time_ms >= 0
