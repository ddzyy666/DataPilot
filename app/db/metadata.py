from typing import Any

from sqlalchemy import Engine, inspect


def inspect_schema(target_engine: Engine) -> dict[str, Any]:
    inspector = inspect(target_engine)
    tables: list[dict[str, Any]] = []

    for table_name in sorted(inspector.get_table_names()):
        primary_key = inspector.get_pk_constraint(table_name).get("constrained_columns", [])
        foreign_keys = [
            {
                "columns": foreign_key.get("constrained_columns", []),
                "referred_table": foreign_key.get("referred_table"),
                "referred_columns": foreign_key.get("referred_columns", []),
            }
            for foreign_key in inspector.get_foreign_keys(table_name)
        ]
        columns = [
            {
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": column["nullable"],
                "primary_key": column["name"] in primary_key,
            }
            for column in inspector.get_columns(table_name)
        ]
        tables.append(
            {
                "name": table_name,
                "columns": columns,
                "foreign_keys": foreign_keys,
            }
        )

    return {
        "dialect": target_engine.dialect.name,
        "table_count": len(tables),
        "tables": tables,
    }

