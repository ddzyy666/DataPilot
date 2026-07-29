from sqlalchemy import create_engine

from app.db.base import Base
from app.db.metadata import inspect_schema
from app.db import models  # noqa: F401


def test_inspect_schema_returns_tables_columns_and_relationships() -> None:
    test_engine = create_engine("sqlite://")
    Base.metadata.create_all(test_engine)

    schema = inspect_schema(test_engine)

    assert schema["dialect"] == "sqlite"
    assert schema["table_count"] == 6

    tables = {table["name"]: table for table in schema["tables"]}
    assert set(tables) == {
        "categories",
        "customers",
        "order_items",
        "orders",
        "products",
        "regions",
    }

    order_columns = {column["name"]: column for column in tables["orders"]["columns"]}
    assert order_columns["id"]["primary_key"] is True
    assert order_columns["paid_at"]["nullable"] is True

    order_foreign_keys = tables["orders"]["foreign_keys"]
    assert {
        "columns": ["customer_id"],
        "referred_table": "customers",
        "referred_columns": ["id"],
    } in order_foreign_keys

