from sqlalchemy import create_engine

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.metadata import inspect_schema
from app.services.schema_formatter import format_schema_for_prompt


def test_format_schema_for_prompt_includes_tables_columns_and_foreign_keys() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)

    schema_context = format_schema_for_prompt(inspect_schema(test_engine))

    assert "数据库方言: sqlite" in schema_context
    assert "表: orders" in schema_context
    assert "- id INTEGER (主键, 非空)" in schema_context
    assert "- customer_id -> customers.id" in schema_context
